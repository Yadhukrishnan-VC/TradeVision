# ADR-028: Portfolio & Capital Management (M4)

**Status:** Proposed
**Date:** 2026-08-03
**Deciders:** Trading Core team (user + architect)
**Depends on:** ADR-002 (event-driven architecture), ADR-013 (event-bus streams), ADR-027 (deterministic risk management — `RiskDecision` capital/exposure reads)

## Context

M3 shipped deterministic risk management that reads capital/exposure through `StubPortfolioStateGateway` — a config-driven stand-in with a guardrail: every read logs a `WARNING` and every persisted `RiskDecision` carries `portfolio_gateway_impl="stub"`, so a stub-backed decision can never back a real order. The audit confirmed `apps.portfolio` was an empty stub, and `apps.accounts.Account` has no balance field. M4 must deliver the **real, authoritative capital/exposure source** so risk decisions are backed by true portfolio state, and a real (paper/manual) position lifecycle exists to feed it.

Three constraints shaped M4:

1. **Unmodified dashboard.** The dashboard's dormant projection consumers (`PositionProjectionService`, `TradeProjectionService`) already define `positions.*` event shapes. Portfolio must publish events matching those contracts exactly — the dashboard is not allowed to change to accommodate Portfolio.
2. **Risk pipeline contract stability.** The M3 `CapitalGateway` / `PortfolioStateGateway` ports must not change; M4 swaps the concrete implementation behind them.
3. **No broker integration.** There is no broker-sync adapter yet. Position changes enter through a manual/paper fill-recording API (`Scope.MANAGE_EXECUTION`), which is the honest placeholder for a future broker-sync adapter — never assumed to be a live execution path.

## Decision

### 1. `apps.portfolio` — authoritative portfolio state (Option A)

New bounded context owning: `AccountCapitalState` (per-account capital ledger), `Position` (open-position write model), `PositionFillExecution` (idempotency log). It is a purely additive extension of `apps.accounts.Account` via a one-to-one `AccountCapitalState` row auto-created by a `post_save` signal (`account_capital_created`) — `apps.accounts` is never modified.

### 2. Capital ledger invariants

- `equity = cash + unrealized_pnl_today`
- `available_capital = cash - margin_used`
- `reserve_margin` is rejected when the reserve would exceed `available_capital` (insufficient-capital invariant).
- Every mutation is a `portfolio.AccountCapitalChanged` event with an append-only `CapitalAdjustmentReason` code (`DEPOSIT`, `WITHDRAWAL`, `MARGIN_RESERVED`, `MARGIN_RELEASED`, `REALIZED_PNL`).
- Mark-to-market ticks persist `unrealized_pnl_today` but publish **no** event (no approved reason code for a pure MTM tick).

### 3. Position lifecycle (ledger style, `PositionLedgerService`)

```
none -> PositionOpened -> PositionQuantityChanged* -> PositionClosed
```

- All position changes flow through `record_fill` (idempotent on `source_fill_id`); `close_position` and `adjust_quantity` are thin wrappers over it — closing can never fork the position logic.
- Opposite-side fills that partially close realize P&L on the closed quantity and continue; over-offset fills close fully, realize on the old quantity, and reopen on the other side (explicit edge case, not a silent assumption).
- `reserve_margin` / `release_margin` / `record_realized_pnl` run in the **same DB transaction** as the position change (one atomic unit, ADR-028 §8).
- The dashboard's locked contracts are preserved: `positions.PositionOpened`, `positions.PositionQuantityChanged`, and a **rich** `positions.PositionClosed` carrying `symbol`, `side`, `entry_price`, `exit_price`, `quantity`, `realized_pnl`, `realized_pnl_pct`, `holding_period_seconds`, `opened_at` (the `TradeProjectionService` contract).

### 4. Real gateways replace the M3 stub

`apps.portfolio.gateways` implements the M3 ports verbatim:

- `RealCapitalGateway` → `CapitalGateway` (available capital, max position size).
- `RealPortfolioStateGateway` → `PortfolioStateGateway` (exposure, daily loss, instrument caps).

Both use `implementation_name = "portfolio_v1"`, so every persisted `RiskDecisionExecution.portfolio_gateway_impl` proves the decision was backed by real portfolio data — fulfilling the ADR-027 guardrail ("when a real portfolio/capital app lands, wiring swaps to it without contract change").

`apps.risk_management.gateways.factory` selects the implementation from `settings.RISK_MANAGEMENT_GATEWAY_IMPL`, **defaulting to `"portfolio"`** (production default is the real gateway so the stub is never the production capital source). The factory keeps a defensive `"stub"` fallback when the setting is absent entirely. The Celery task `evaluate_rule_firing` now uses the factory instead of constructing the stub directly.

### 5. Single-account resolution (ADR-028 §2.8)

Read endpoints and gateways resolve the primary account as `Account.objects.filter(is_default=True).order_by("-created_at").first()`, or an explicitly pinned `account_id`. Missing account ⇒ `None` ⇒ fail-closed (`MISSING_ACCOUNT_STATE` in risk).

### 6. Decimal precision convention

All money fields are `DecimalField(max_digits=20, decimal_places=8)` (dashboard-precision). `Decimal` arithmetic on two 8-dp values yields 16 dp, which fails the field's validation; `quantize_money()` rounds to `Decimal("0.00000001")` at **every persistence boundary**. Event payloads are rendered in natural numeric form (`format(value.normalize(), "f")` → `"200"`, not `"200.00000000"`) because dashboard consumers parse `Decimal(str(...))`.

### 7. Events

| Event type | Trigger | Notes |
|---|---|---|
| `positions.PositionOpened` | fill opens a position | dashboard `PositionProjectionService` contract (unmodified) |
| `positions.PositionQuantityChanged` | scale-in / partial close | dashboard `PositionProjectionService` contract |
| `positions.PositionClosed` | full close / over-offset flip | rich payload feeds dashboard `TradeProjectionService` (unmodified) |
| `portfolio.AccountCapitalChanged` | any capital ledger mutation | `cash`, `margin_used`, `equity`, `available_capital`, `reason` |
| `portfolio.ExposureChanged` | after every applied fill | recomputed from the open positions |

Correlation/causation: `correlation_id` is the triggering fill/adjustment id (or the originating `RiskApproved.correlation_id` when a fill responds to an approved risk decision); `causation_id` is the immediate cause event id.

### 8. Portfolio API

- `GET /api/v1/portfolio/` — authoritative capital state for the primary account (`read:portfolio`).
- `GET /api/v1/portfolio/positions/` — open positions with live price / unrealized / exposure (`read:portfolio`).
- `POST /api/v1/portfolio/fills/` — record a manual/paper fill (`manage:execution`); returns `201` applied, `200` duplicate-skipped, `400` on domain error.

All views use `Scope.READ_PORTFOLIO` / `Scope.MANAGE_EXECUTION` (both pre-existing). M4 also fixes the latent `permission_classes = [HasAPIKeyScope.with_scope(...)]` bug (an *instance* in a list DRF instantiates ⇒ `TypeError` on every request) in both `apps.portfolio` and `apps.risk_management` by introducing scope-wrapper permission classes matching the dashboard convention.

## Architecture

```
apps.portfolio/
  apps.py                      # PortfolioConfig, ready() -> account_signals
  domain/
    entities.py                # (position/capital domain helpers)
    value_objects.py           # Side, direction_sign, opposite_side, CapitalAdjustmentReason
    exceptions.py              # PortfolioDomainError, InvalidFillError, InsufficientCashError, ...
  application/
    capital_service.py         # CapitalService — authoritative ledger (ADR-028 §2.2, §2.3)
    position_ledger_service.py # PositionLedgerService — fill lifecycle (ADR-028 §2.5, §2.6)
    portfolio_query_service.py # PortfolioQueryService — aggregations/exposure/current price
  infrastructure/
    models.py                  # AccountCapitalState, Position, PositionFillExecution + quantize_money
    repositories.py            # AccountCapitalRepository, PositionRepository, PositionFillExecutionRepository
    event_publishers.py        # PortfolioEventPublisher (5 approved events, _fmt natural form)
    account_signals.py         # post_save Account -> zero-balance AccountCapitalState
    price_source.py            # MarketDataCurrentPriceProvider (fail-open, ADR-028 §2.6/§2.7)
    migrations/0001_initial.py
  interfaces/api/
    permissions.py             # HasReadPortfolio, HasManageExecution (wrapper classes)
    views.py                   # PortfolioSummaryView, PositionsListView, RecordFillView
    serializers.py             # AccountCapitalSerializer, PositionSerializer, FillRequestSerializer
    urls.py
  gateways/
    real_capital_gateway.py         # CapitalGateway impl ("portfolio_v1")
    real_portfolio_state_gateway.py # PortfolioStateGateway impl ("portfolio_v1")
```

## Persistence

- `AccountCapitalState`: one-to-one with `apps.accounts.Account`; fields `cash`, `margin_used`, `equity`, `available_capital`, `realized_pnl_today`, `unrealized_pnl_today` (all `Decimal(20,8)`).
- `Position`: one row per **open** position per `(account_id, symbol)` — closing removes the row, so a plain unique constraint is the "unique while open" guarantee.
- `PositionFillExecution`: `source_fill_id` unique — the natural-key idempotency guard mirroring `RuleExecution` / `RiskDecisionExecution`.

## Application services

- `CapitalService` — `deposit` / `withdraw` / `reserve_margin` / `release_margin` / `record_realized_pnl` / `reconcile_unrealized`; the **only** entry point for capital changes (ADR-028 §21).
- `PositionLedgerService` — `record_fill` / `close_position` / `adjust_quantity`, all idempotent on `source_fill_id`, one DB transaction per applied fill.
- `PortfolioQueryService` — `get_account_capital`, `get_available_capital`, `get_exposure`, `get_unrealized_pnl`, `get_open_positions`, `get_current_price` (fail-open via `MarketDataCurrentPriceProvider`).

## Acceptance checklist

- [x] `Account` created ⇒ zero-balance `AccountCapitalState` created via signal (ADR-028 §19), zero modification to `apps.accounts`.
- [x] Unit tests: `CapitalService` invariants (deposit/withdraw/reserve/release/realized, insufficient-capital rejections, quantize-at-boundary), position lifecycle (open/add/partial-close/full-close/over-offset flip), gateways conformance (real impls satisfy the M3 ports, `implementation_name == "portfolio_v1"`).
- [x] Integration: `record_fill` drives the **unmodified** dashboard `PositionSnapshot` projection (opened/closed/scaled); real `RiskEvaluationService` run with the `"portfolio"` gateways reaches `RiskApproved` (funded default account) or `MISSING_ACCOUNT_STATE` (unfunded); correlation/causation propagate.
- [x] API integration tests: summary / positions / fills endpoints; scope enforcement (403 without scope, 404 without primary account), natural-form decimals, duplicate-fill idempotency, `400` on domain errors.
- [x] Risk API permission fix proven: decision list + kill-switch endpoints 200/403 per scope (previously `TypeError` on every request).
- [x] `manage.py check` clean; `makemigrations --check` clean.
- [x] Dashboard + eventbus suite: no new failures vs M3 baseline (41→37 pre-existing failures; the 4 `position_projection` tests now pass via the pre-existing `UUID` import fix). Full suite strictly better than M3 (914 vs 810 passed).
- [x] Zero modification outside: new `apps.portfolio`, `config/settings/base.py` (registration + `RISK_MANAGEMENT_GATEWAY_IMPL`), `config/urls.py` (portfolio API mount), `apps.risk_management` (gateway factory + tasks wiring + permission fix + tests), and the user-approved one-line `UUID` import in dashboard's `position_projection_service.py`.

## Definition of done

- All M4 code merged as Batch M4 on `trading-core`.
- Risk decisions backed by real portfolio data by default (`RISK_MANAGEMENT_GATEWAY_IMPL="portfolio"`); the stub remains only as a defensive fallback and never the production default.
- No broker/execution integration; `POST /fills/` is a manual/paper entry point gated by `manage:execution`, never a live execution path.
- Dashboard projection consumers run unmodified against the new `positions.*` events.
- No modification to the existing `intelligence → dashboard` risk-context (AI) pipeline.

## Out of scope

- Broker-sync adapter / live execution (the `RecordFillView` is the honest placeholder).
- Options chain analysis (Phase 9 dashboard work).
- Portfolio drawdown alerts, P&L history beyond today's realized/unrealized tallies.
- The 37 pre-existing dashboard/eventbus test failures and 3 pre-existing `rule_engine` failures (documented in PROJECT_STATE.md; not introduced by M4).
