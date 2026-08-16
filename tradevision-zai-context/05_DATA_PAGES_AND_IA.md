# 05 — Data Models, Pages/Views, and Information Architecture

## Data Models (Entities the UI Renders)

Verified from Django model definitions. JSON representations are produced by DRF serializers (see 04). All IDs are UUID strings unless noted.

### User & Account (VERIFIED)

- `accounts.User` (`AUTH_USER_MODEL`): UUID `id`, `username` (unique, default `""`), `role` ∈ {owner, staff, viewer} (default viewer), plus Django auth fields (`is_active`, `is_staff`, `date_joined`, ...). SOURCE: `backend/apps/accounts/infrastructure/models.py`, `backend/config/settings/base.py:21`
- `accounts.Account`: trading account, `owner` FK → User, `name`, `is_default` bool. Backtest/edge/WF/cost runs each create an isolated `Account` (`is_default=False`) named per the run. SOURCE: `backend/apps/accounts/infrastructure/models.py`, used in `backend/apps/backtesting/interfaces/api/views.py:45`

### Market Data (VERIFIED)

- `market_data.Instrument` (table `market_data_instrument`): `instrument_token` BigInteger PK (exchange-assigned), `exchange` CharField(10) indexed, `tradingsymbol` CharField(100), `name`, `segment`, `lot_size` (int, default 1), `tick_size` (Decimal, default 0.05), `instrument_type`, `expiry` (nullable), `is_active` bool default True; unique (`exchange`, `tradingsymbol`). SOURCE: `backend/apps/market_data/infrastructure/models.py:10`
- `market_data.Candle` (table `market_data_candle`): `id` BigAutoField PK, `instrument` FK → Instrument, `timeframe` CharField(10) indexed, `timestamp` DateTime, OHLCV columns (open/high/low/close/volume). SOURCE: `backend/apps/market_data/infrastructure/models.py:89`

### Technical Analysis (VERIFIED)

- `technical_analysis.TASnapshot` (table `technical_analysis_tasnapshot`): UUID `id`, `symbol` indexed, `exchange`, `timeframe` (e.g. "15min", "1D"), `pine_id` (indexed, TradingView Pine Script id), `pine_version`, plus OHLCV and raw payload fields. SOURCE: `backend/apps/technical_analysis/infrastructure/models.py:10`

### Rule Engine (VERIFIED)

- `rule_engine.RuleConfig` (table `rule_engine_ruleconfig`): `rule_id` (unique, indexed), `enabled` bool default True, `parameters` JSON default `{}`, `severity_override` (null/blank; LOW|MEDIUM|HIGH|CRITICAL), `validated_regimes` JSON default `{}` — holds ADR-029 validation results (`{"<regime>": "GO"|"NO_GO"|"INSUFFICIENT_DATA"}`). SOURCE: `backend/apps/rule_engine/infrastructure/models.py:10`
- `rule_engine.RuleExecution` (table `rule_engine_ruleexecution`): `analysis_event_id` UUID, `rule_id` (indexed), `symbol` (indexed), `severity`, `trigger_data` JSON, `published_event_id` nullable; unique constraint on (`analysis_event_id`, `rule_id`). SOURCE: `backend/apps/rule_engine/infrastructure/models.py:41`
- Rule IDs (VERIFIED, 8 built-in): `breakout_v1`, `high_beta_breakout_v1`, `long_momentum_v1`, `price_movement_v1`, `short_breakdown_v1`, `short_sell_v1`, `volatility_breakout_v1`, `volume_spike_v1`. SOURCE: `backend/apps/rule_engine/domain/rules/*.py` (`def rule_id`)

### Execution (VERIFIED)

- `execution.Order`: account FK, symbol, side (LONG/SHORT), quantity, entry_price, avg_fill_price, filled_quantity, status (CREATED/SUBMITTED/ACKNOWLEDGED/...), `correlation_id` (links to the rule firing event). SOURCE: `backend/apps/execution/infrastructure/models.py`, used in `backend/apps/backtesting/services.py:178`
- `execution.Fill`, `execution.ExecutionRequest`: fills and requests (status REJECTED_* for risk-rejected). SOURCE: same app.

### Portfolio (VERIFIED)

- `portfolio.AccountCapitalState`: per-account `equity`, `available_capital` (used by `run_stats` for `equity_at_completion` / `available_capital`). SOURCE: `backend/apps/portfolio/infrastructure/models.py`, `backend/apps/backtesting/services.py:232`
- `portfolio.Position`: holdings (quantity, avg_cost, market_value, unrealized_pnl, opened_at) surfaced via `HoldingSerializer`. SOURCE: `backend/apps/portfolio/infrastructure/models.py`

### Backtesting (VERIFIED)

- `backtesting.BacktestRun` (table `backtest_backtestrun`): `symbol`, `timeframe`, `range_start`, `range_end`, `account` OneToOne → Account, `status` ∈ PENDING/RUNNING/COMPLETED/FAILED, `commission_rate` Decimal(10,6) default 0.0003, `slippage_bps` Decimal(10,4) default 5.0, `in_sample_ratio` default 0.70, `net_pnl`, `expectancy`, `profit_factor`, `max_drawdown`, `sharpe_ratio`, `sortino_ratio`, `benchmark_return`, `risk_rejected_count`, `failure_reason`, `started_at`, `completed_at`, `last_processed_snapshot_id`. SOURCE: `backend/apps/backtesting/models.py` (112 lines), `backend/apps/backtesting/services.py:643-651`

### Metrics Primitives (VERIFIED)

Pure functions in `backend/apps/backtesting/domain/metrics.py`: `calculate_expectancy`, `calculate_profit_factor`, `calculate_max_drawdown`, `calculate_sharpe_ratio`, `calculate_sortino_ratio`, `calculate_benchmark_return`. Used by `BacktestStatsService.run_stats` for every bucket. SOURCE: `backend/apps/backtesting/domain/metrics.py:14-128`

## Pages and Views (Frontend Page Map)

Status per page: ✅ READY (all data comes from verified endpoints) · ⚠ PARTIAL (some data verified, some ⚠) · ❌ GAP (no backend data source).

### Auth & Shell

| Page | Route | Data source | Status |
|---|---|---|---|
| Login | `/login` | `POST /auth/login/`, `POST /auth/refresh/` | ✅ (contract verified; see 03 auth caveat) |
| App shell | `/` | global nav, role from `/auth/me/` | ✅ (auth P0 resolved) |

### Dashboard

| Page | Route | Data source | Status |
|---|---|---|---|
| Dashboard Home | `/` | `GET /dashboard/home/summary/` | ✅ |
| Portfolio Composition | `/portfolio` | `GET /dashboard/portfolio/composition/` | ✅ |
| Holdings detail | `/portfolio/holdings/:symbol` | `GET /dashboard/portfolio/holdings/:symbol/` | ✅ |
| Live Positions | `/positions` | `GET /dashboard/positions/live/` | ✅ |
| Position detail | `/positions/:id` | `GET /dashboard/positions/live/:id/` | ✅ |
| Orders | `/orders` | `GET /dashboard/orders/` | ✅ |
| Order detail | `/orders/:id` | `GET /dashboard/orders/:id/` | ✅ |
| Trade History | `/trades` | `GET /dashboard/trades/history/` | ✅ |
| Trade export status | `/trades/export/:id` | `GET /dashboard/trades/history/export/:id/` | ⚠ |
| Open Trades | `/trades/open` | `GET /dashboard/trades/open/` | ✅ |
| Closed Trades | `/trades/closed` | `GET /dashboard/trades/closed/` | ✅ |

### Analytics & Risk (per account)

| Page | Route | Data source | Status |
|---|---|---|---|
| PnL Analytics | `/analytics/:accountId/pnl` | `GET /dashboard/accounts/:accountId/pnl` | ⚠ |
| Daily Rollup | `/analytics/:accountId/pnl/daily` | `GET /dashboard/accounts/:accountId/pnl/daily` | ⚠ |
| Performance | `/analytics/:accountId/performance` | `GET /dashboard/accounts/:accountId/performance` | ⚠ |
| Risk Summary | `/analytics/:accountId/risk` | `GET /dashboard/accounts/:accountId/risk` | ⚠ |

### Research / Backtesting (core differentiator)

| Page | Route | Data source | Status |
|---|---|---|---|
| Backtest Runs (list + create) | `/research/backtests` | `POST /backtesting/runs/`, poll `GET /backtesting/runs/:id/` | ✅ |
| Backtest Run Detail | `/research/backtests/:id` | `GET /backtesting/runs/:id/` (`stats`) | ✅ |
| Walk-Forward | `/research/walk-forward` | `POST /backtesting/walk-forward/` | ✅ |
| Edge Validation | `/research/edge-validation` | `POST /backtesting/edge-validation/` | ✅ |
| Cost Sensitivity | `/research/cost-sensitivity` | `POST /backtesting/cost-sensitivity/` | ✅ |

### Rule Engine & Monitoring

| Page | Route | Data source | Status |
|---|---|---|---|
| Rule Configs | `/rules` | `GET /rule-engine/configs/` | ⚠ |
| Rule Config detail | `/rules/:ruleId` | `GET /rule-engine/configs/:ruleId/` | ⚠ |
| Rule Executions | `/rules/executions` | `GET /rule-engine/executions/` | ⚠ |

### Journals & Compliance

| Page | Route | Data source | Status |
|---|---|---|---|
| Trade Journal | `/journal` | `GET /journal/entries/` | ⚠ |
| Journal Entry detail | `/journal/:correlationId` | `GET /journal/entries/:correlationId/` | ⚠ |
| Audit Log | `/audit` | `GET /audit/entries/` | ⚠ |
| Pipeline Health | `/health` | `GET /pipeline-health/` | ⚠ |

### Secondary

| Page | Route | Data source | Status |
|---|---|---|---|
| Recommendations | `/recommendations` | `GET /recommendations/` + accept/reject/explanation | ⚠ |
| Signals | `/signals` | `GET /signals/` | ⚠ |
| Pattern Analysis Runs | `/patterns` | `GET /pattern-engine/runs/` | ⚠ |
| Watchlist | `/watchlist` | `GET /watchlist/` | ✅ endpoints |
| Portfolio summary | `/portfolio/summary` | `GET /portfolio/` | ⚠ |
| Risk decisions | `/risk` | `GET /risk-management/decisions/` | ⚠ |
| Kill switch | `/risk/kill-switch` | `GET/POST /risk-management/kill-switch/...` | ⚠ |
| Drift / Reconciliation | `/reconciliation` | `GET /portfolio-reconciliation/drift/` + `drift/summary/` | ⚠ |
| Trader Memory | `/memory` | `GET /trader-memory/entries/`, `projections/:strategyId/` | ⚠ |

### Explicitly NOT pages (never build)

- Market data OHLC chart by symbol — NO HTTP endpoint exposes candles; the only market-data access is inside backtest replay. ❌ GAP (see 08).
- Raw webhook submission UI (TradingView/Chartink/TA webhooks) — token-protected, provider-facing, not for the dashboard.

### Cross-cutting notes

- All research/analytics endpoints are POST-based analysis jobs that run synchronously and can be slow (full-range backtests). Show loading states with clear progress text.
- Account ids come from run creation responses and dashboard responses; the UI needs an account context (default = the user's default account from `/auth/me/` — ✅ now available once authenticated).

## Navigation and Information Architecture

### Top-level IA

```
App Shell (top nav)
├── Dashboard          → home summary, portfolio composition, live positions, orders, trade history
│   ├── Portfolio      → composition + per-symbol holdings
│   ├── Positions      → live positions list/detail
│   ├── Orders         → orders list/detail
│   └── Trades         → history, open, closed, export
├── Analytics & Risk   → per-account PnL, daily rollup, performance, risk summary
├── Research           → Backtests, Walk-Forward, Edge Validation, Cost Sensitivity
├── Rules              → Rule Configs, Rule Executions
├── Journal            → trade journal entries
├── Memory             → trader memory entries + strategy projections
├── Signals            → signals list
├── Recommendations    → recommendations + accept/reject/explanation
├── Patterns           → pattern engine runs + historical vectors
├── Watchlist          → watchlist
└── System             → Audit Log, Pipeline Health, Risk decisions, Kill switch, Reconciliation, Health
```

### Navigation decisions

1. **Left sidebar** for primary nav (Dashboard, Analytics, Research, Rules, Journal, System), **top bar** for user/meta (profile, role badge, logout). Sidebar collapses to icons on small screens.
2. **Research section** is the product differentiator — give it the most prominent placement (sub-nav with 4 tabs: Backtests / Walk-Forward / Edge Validation / Cost Sensitivity).
3. **Account context** is global: when multiple accounts exist (each backtest run creates its own account), the top bar shows the active account id, and Analytics/Risk routes carry `:accountId`. Default account comes from `/auth/me/` when available.
4. **Rule-centric linking**: every `trades[]` record in a backtest result has a `correlation_id`; rule executions list by `rule_id`. Link Trade History ↔ Rule Executions by rule_id where data permits (⚠ bodies not fully verified — degrade gracefully).
5. **Breadcrumbs** on detail pages: `Research / Backtests / <run_id>`.
6. Deep-linkable: every detail page has a stable route (ids are UUIDs).

### Route table

Full route list is in the Pages and Views section above. Reserve a top-level `*` not-found route → redirect to Dashboard.

### UI strings / conventions

- Symbols uppercased by backend (`symbol.upper()`); display as given.
- Regime names are arbitrary strings stored in `trigger_data["regime"]` — render as chips, never assume a fixed set.
- Rule ids (`breakout_v1`, etc.) are stable constants (see Data Models above) — use them for icons/labels, but render the raw id too (rules are data-driven).