# ADR-027: Deterministic Risk Management (M3)

**Status:** Proposed
**Date:** 2026-08-02
**Deciders:** Trading Core team (user + architect)
**Depends on:** ADR-002 (event-driven architecture), ADR-013 (rule engine / RuleFired contract), M2 (deterministic setups)

## Context

M2 shipped deterministic trading setups (Long Momentum, Short Sell, Volatility Breakout) that fire `rule_engine.RuleFired` events. Those setups contain stop-loss, entry price, and direction, but **nothing yet evaluates risk**: no capital check, no position sizing, no exposure/daily-loss limits, no kill switch. The audit verified `apps.risk_analysis` and `apps.portfolio` are empty stubs — neither can serve capital/exposure data today.

Three open blockers block a trade-safe M3:

1. **Capital source** — there is no real capital/exposure producer (accounts have no balance field, portfolio app is empty).
2. **Entry price** — the M2 rules did not emit `entry_price` in `trigger_data`, so no deterministic sizing is possible.
3. **Kill switch scope** — a trade-safety kill switch was deferred; its shape (GLOBAL/ACCOUNT/SYMBOL) and persistence model are undecided.

## Decision

Three Option A choices, matching the acceptance checklist below.

### 1. Stub capital gateway (Option A — guarded)

Implement `StubPortfolioStateGateway` implementing the `PortfolioStateGateway` protocol (capital + exposure + daily loss + instrument caps). Values come from `settings.RISK_MANAGEMENT`. Every read logs a structured `WARNING` ("non_production_capital_source") and every persisted `RiskDecision` records `implementation_name = "stub"`.

**Guardrail:** the stub never backs a real order. It is a data source for risk *evaluation* only; `implementation_name` on every decision makes any downstream misuse auditable. When a real portfolio/capital app lands, wiring swaps to it without contract change.

### 2. Add `entry_price` to `RuleFired.trigger_data` (Option A — additive amendment to M2)

Each M2 setup rule (Long Momentum, Short Sell, Volatility Breakout) already receives `current_price`; add `trigger_data["entry_price"] = str(current_price)` to all three. This is an additive patch to the already-merged M2 — no schema change, no new persistence, backwards compatible.

### 3. Kill switch in M3 (Option A — Postgres-backed, cache read-through)

- Scopes: `GLOBAL` → `ACCOUNT` → `SYMBOL` (most-specific wins for "is this trade blocked").
- Persistence: `KillSwitchState` rows (scope, symbol nullable, is_active, activated/deactivated timestamps, actor, reason), one active row per scope+symbol enforced by a partial unique constraint on active rows.
- Read path: short-TTL `KillSwitchCache` (Redis, ~10s TTL); **fail-closed** — any cache/db lookup error ⇒ treat kill switch as active.
- Evaluated **first** in the risk pipeline (before any capital math).
- Toggles are real domain events (`risk_management.KillSwitchActivated` / `KillSwitchDeactivated`), which the existing `apps.audit_log` `"*"` subscriber records for free.
- API gated by the already-existing, currently-unused `Scope.MANAGE_RISK_POLICY = "manage:risk_policy"`.

## Architecture

```
apps.risk_management/
  __init__.py
  apps.py                      # RiskManagementConfig, ready() -> register_all_handlers
  domain/
    __init__.py
    entities.py                # RiskDecision, RiskRejection, KillSwitchToggle
    value_objects.py           # RejectionReason, RiskDecisionStatus, KillSwitchScope
    events.py                  # RiskApproved, RiskRejected, KillSwitchActivated, KillSwitchDeactivated
    exceptions.py              # RiskEvaluationError, RiskConfigNotFound, RiskConfigConflict
    rules/
      __init__.py              # exports all 8 checks
      base_risk_check.py       # RiskCheckContext, RiskCheckResult, RiskCheck (fail-closed safe_evaluate)
      kill_switch_check.py     # KILL_SWITCH_ACTIVE
      data_freshness_check.py  # STALE_DATA
      market_session_check.py  # MARKET_CLOSED
      stop_direction_check.py  # MISSING_STOP_LOSS / MISSING_ENTRY_PRICE / STOP_EQUALS_ENTRY / STOP_WRONG_SIDE / ZERO_RISK_DISTANCE
      position_sizing.py       # MISSING_ACCOUNT_STATE / ZERO_CAPITAL / INSUFFICIENT_CAPITAL / POSITION_SIZE_ZERO
      exposure_limits.py       # MAX_EXPOSURE_EXCEEDED
      daily_loss_limit.py      # DAILY_LOSS_LIMIT_EXCEEDED
      risk_reward_check.py     # RISK_REWARD_BELOW_MINIMUM
      instrument_check.py      # INVALID_INSTRUMENT
  application/
    __init__.py
    ports.py                   # CapitalGateway, PortfolioStateGateway, MarketStatusGateway (Protocols)
    risk_config.py             # RiskConfig + risk_config_from_settings()
    risk_evaluation_service.py # RiskEvaluationService
    kill_switch_service.py     # KillSwitchService
  infrastructure/
    __init__.py
    models.py                  # RiskDecisionExecution, KillSwitchState
    repositories.py            # RiskDecisionRepository, KillSwitchStateRepository
    cache.py                   # KillSwitchCache (short-TTL, fail-closed)
    tasks.py                   # evaluate_rule_firing (Celery)
    event_handlers.py          # SUBSCRIBED_EVENTS = {"rule_engine.RuleFired": [...]}
    migrations/
      __init__.py
  interfaces/
    __init__.py
    api/
      __init__.py
      views.py                 # gated by Scope.MANAGE_RISK_POLICY
      serializers.py
      urls.py
  gateways/
    __init__.py
    stub_portfolio_state_gateway.py
```

## Entities

- `RiskDecision` (domain entity): decision_id, analysis_event_id, rule_id, event_type, symbol, occurred_at, status (RiskDecisionStatus), entry_price, stop_loss, position_size, risk_amount, risk_pct_of_capital, risk_reward_ratio, rejection (RiskRejection | None), reason_message, trigger_data, portfolio_gateway_impl.
- `RiskRejection`: code (RejectionReason), message.
- `RiskDecisionStatus`: APPROVED | REJECTED.
- `KillSwitchToggle`: scope, symbol (optional), actor, active (bool), reason, toggled_at.
- `KillSwitchScope`: GLOBAL | ACCOUNT | SYMBOL.

## Persistence

`RiskDecisionExecution` mirrors `RuleExecution`:

- `UniqueConstraint(analysis_event_id, rule_id)` — the idempotency contract.
- `create_from_assessment` catches `IntegrityError`/`ValidationError` ⇒ `None` ⇒ duplicate skipped.
- `mark_published` scoped per `rule_id`.
- `portfolio_gateway_impl` column on every row.

`KillSwitchState`:

- scope, symbol (null for GLOBAL/ACCOUNT), is_active, activated_at, deactivated_at, actor, reason.
- Partial unique constraint: at most one active row per (scope, symbol).

## Events

| Event type | Trigger | Payload (subset) |
|---|---|---|
| `risk_management.RiskApproved` | Approved decision | symbol, rule_id, event_type, entry_price, stop_loss, position_size, risk_amount, risk_pct_of_capital, risk_reward_ratio, portfolio_gateway_impl |
| `risk_management.RiskRejected` | Rejected decision | symbol, rule_id, event_type, reason_code, reason_message, portfolio_gateway_impl (no position_size) |
| `risk_management.KillSwitchActivated` | Toggle on | scope, symbol, actor, reason, activated_at |
| `risk_management.KillSwitchDeactivated` | Toggle off | scope, symbol, actor, reason, deactivated_at |

Correlation/causation: `correlation_id = RuleFired.analysis_event_id`, `causation_id = RuleFired.event_id`. Both `RiskApproved` and `RiskRejected` carry `portfolio_gateway_impl`.

## Application services

- `RiskEvaluationService` — assembles `RiskCheckContext` from a `RuleFired` payload + gateways + config; runs 8 checks in fixed order (KillSwitch → DataFreshness → MarketSession → Instrument → StopDirection → PositionSizing → Exposure → DailyLoss → RiskReward); first rejection wins; **fails closed with `RejectionReason.UNKNOWN`** on any unexpected error.
- `KillSwitchService` — `is_active(scope, symbol)`, `activate(...)`, `deactivate(...)`; read-through short-TTL cache; persists `KillSwitchState`; publishes toggle events.

## Infrastructure notes

- Celery task `tradevision.risk_management.evaluate_rule_firing` consumes the RuleFired payload; persistence + event publish happen inside one task with idempotency (duplicate ⇒ skip, never double-publish).
- Handlers registered under consumer group `risk_management`.
- The `apps.audit_log` `"*"` subscriber already persists every `risk_management.*` event → kill-switch toggles and every decision get an immutable audit trail with zero new audit code.

## Acceptance checklist

- [x] `trigger_data["entry_price"]` present in all three M2 setup rules' RuleFired events (regression test per rule).
- [ ] Unit tests: each `RejectionReason` reachable; kill-switch evaluated first; fail-closed on cache/db lookup error; idempotent duplicate delivery; correlation/causation propagation; Decimal-only sizing (no float).
- [ ] Integration test: `rule_engine.RuleFired` → `RiskApproved` or `RiskRejected` on FakeEventBus.
- [ ] `KillSwitchState` partial-unique: activating the same scope+symbol twice yields one active row.
- [ ] Audit proof: `KillSwitchActivated` toggle produces an `AuditLogEntry`.
- [ ] `manage.py check` clean; `makemigrations --check` clean; ruff clean.
- [ ] Zero modification outside: the three M2 rule files, their tests, `config/settings/base.py` (registration + `RISK_MANAGEMENT`), and the new `apps.risk_management` package.
- [ ] Stub-gateway guardrail: every persisted decision carries `portfolio_gateway_impl == "stub"`.

## Definition of done

- All M3 code merged as Batch M3 on `trading-core`.
- No broker/execution integration; stub never backs a real order.
- No LLM involvement in any risk decision; fully deterministic.
- No modification to the existing `intelligence → dashboard` risk-context (AI) pipeline.

## Out of scope

- Real capital/exposure source (portfolio app, broker sync, MTM engine).
- Order/execution integration; risk decisions are advisory signals only.
- 2026 NSE holiday list (bundled calendar covers 2024–2025).
- Pre-existing CI failures / dependency drift from the M2 audit.
