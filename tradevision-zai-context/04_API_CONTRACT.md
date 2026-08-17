# 04 — API Contract (Verified Endpoints + Response Shapes)

Base URL: `/api/v1`. All responses are JSON. Errors follow `{"error": {code, message, details?}}` (see 01). Most list endpoints paginate with `{count, next, previous, results}` (PAGE_SIZE=20); exceptions that return **bare arrays** are flagged per-section (notably journal `entries/`, rule-engine `configs/` + `executions/`, portfolio `positions/`).
Numeric Decimal fields are serialized as **strings** (`str(...)`), not JSON numbers. Treat them as strings and convert client-side.

Legend: ✅ = exact shape verified in source · ⚠ = endpoint verified, exact body requires verification.

---

## Auth — `/api/v1/auth/` (all ✅ VERIFIED live + in source)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `login/` (alias `token/`) | `{"username","password"}` | 200 `{"access","refresh","user":{...}}`; 401 `{"error":{code,message}}` |
| POST | `refresh/` (alias `token/refresh/`) | `{"refresh"}` | 200 `{"access","refresh"}`; 401 error |
| GET | `me/` | — | 200 `{"id","username","role","date_joined"}` |
| GET | `api-keys/` | — | 200 `{count,next,previous,results:[{id,scopes,...}]}` |
| POST | `api-keys/` | `{"scopes":["..."]}` | 201 `{"id","raw_key","scopes",...}` (raw shown once); 400 on invalid/empty scopes |
| DELETE | `api-keys/<uuid:pk>/` | — | 204 |
| GET | (any scope-gated endpoint) | `Authorization: Api-Key <raw>` | revoked key → 401 `{"detail":"API key has been revoked"}` (ErrorDetail code `api_key_revoked`) |

SOURCE: `backend/apps/accounts/interfaces/api/views.py`, `urls.py`

Auth model (verified live): session/identity endpoints use JWT Bearer; scope-gated endpoints accept JWT (authorized by role: read scopes = any authenticated user, `manage:` scopes = owner/staff) OR a scoped API key (scope enforced). Revoked/invalid keys → 401.

---

## Health — `/api/v1/health/` (✅ VERIFIED)

`GET /` liveness; `GET db/`, `cache/`, `celery/`, `eventbus/`, `system/`. Unauthenticated, not throttled.
SOURCE: `backend/apps/health/urls.py`

---

## Dashboard — Trading Core `/api/v1/dashboard/` (shapes ✅ VERIFIED live)

| Method | Path | Response shape (serializer) |
|---|---|---|
| GET | `home/summary/` | `DashboardHomeSummarySerializer`: `account_id, open_positions_count, open_orders_count, today_realized_pnl, today_unrealized_pnl, active_alerts_count, broker_connection_status, market_session_status, last_updated_at`; 404 `account-summary-not-initialized` when no row yet |
| GET | `portfolio/composition/` | `account_id, holdings[], total_market_value, total_cost_basis, cash_balance`; holdings items: `account_id, symbol, quantity, avg_cost, cost_basis, market_value, allocation_pct, unrealized_pnl, opened_at` |
| GET | `portfolio/holdings/<symbol>/` | `HoldingSerializer`: `account_id, symbol, quantity, avg_cost, cost_basis, market_value, allocation_pct, unrealized_pnl, opened_at` |
| GET | `positions/live/` | paginated `{count?,next,previous,results}`; item = `PositionSnapshotSerializer`: `position_id, account_id, symbol, side, quantity, entry_price, current_price, unrealized_pnl, unrealized_pnl_pct, is_open, opened_at, closed_at` |
| GET | `positions/live/<position_id>/` | single position snapshot |
| GET | `orders/` | paginated; item = `OrderSnapshotSerializer`: `order_id, account_id, symbol, side, order_type, status, quantity, filled_quantity, avg_fill_price, limit_price, placed_at` |
| GET | `orders/<order_id>/` | single order snapshot |
| GET | `trades/history/` | paginated; item = `TradeRecordSerializer`: `trade_id, account_id, symbol, side, entry_price, exit_price, quantity, realized_pnl, realized_pnl_pct, opened_at, closed_at, holding_period_seconds` |
| POST | `trades/history/export/` | 202 `ExportJobSerializer`: `export_id, status:"pending", format, file_url:null, requested_at:null, completed_at:null, error_message:null`; request `ExportRequestSerializer` (`format` "csv"/"pdf" + optional filters). Note: enqueues a Celery task — requires a broker/worker; without one, staging returns 500 from the AMQP router (see GAPS). |
| GET | `trades/history/export/<export_id>/` | `ExportJobSerializer` status |
| GET | `trades/open/` | open-trades list (position-shaped items) |
| GET | `trades/closed/` | closed trades list (trade-shaped items) |

SOURCE: `backend/apps/dashboard/interfaces/api/trading_core/urls.py`, `serializers.py`, `views.py`

Verified live 2026-08-16: all of the above returned 200 with the listed shapes (empty collections where no data; `home/summary/` 404 until a `DashboardHomeSummary` row exists). Filters are enforced via `DjangoFilterBackend` on `positions/live/`, `orders/`, `trades/history/` (invalid filter value → 400).

---

## Dashboard — Analytics & Risk `/api/v1/dashboard/accounts/<account_id>/` (✅ VERIFIED live)

| Method | Path | Purpose | Verified body |
|---|---|---|---|
| GET | `pnl` | PnL analytics | `{current_total_pnl, current_unrealized_pnl, peak_cumulative_pnl, current_drawdown_pct, time_series[], metadata:{period, point_count}}` |
| GET | `pnl/daily` | Daily rollup | array of `{trading_date, realized_pnl, total_pnl, cumulative_pnl}`; requires `?date_from=&date_to=` (400 if absent) |
| GET | `performance` | Performance metrics | `{period, win_rate, avg_win, avg_loss, profit_factor|null, expectancy, sharpe_like_ratio|null, total_trades, winning_trades, losing_trades}` |
| GET | `risk` | Risk summary | `{total_exposure, largest_position_pct, sector_concentration_pct, leverage_ratio, active_alerts[]}` |

SOURCE: `backend/apps/dashboard/interfaces/api/analytics_risk/urls.py`, `views.py`

Note: there is NO dedicated equity-curve endpoint — the equity/returns chart is sourced from `pnl/daily` (`total_pnl` cumulative) or backtesting `run_stats.equity_at_completion`.

---

## Journal — `/api/v1/journal/` (✅ VERIFIED live 2026-08-17)

| Method | Path | Purpose | Verified body |
|---|---|---|---|
| GET | `entries/` | List journal entries (requires `?account_id=<uuid>`) | **BARE ARRAY** (NOT paginated) of `JournalEntrySerializer` items (below); 400 `{"error":{"code":"missing_account_id","message":"account_id query parameter is required."}}` when `account_id` missing |
| GET | `entries/<uuid:correlation_id>/` | One entry by correlation_id | ⚠ currently ALWAYS 500: `views.py:37` calls `uuid.UUID(correlation_id)` on a value the `<uuid:>` route already converted to `UUID` → `AttributeError: 'UUID' object has no attribute 'replace'`; the 404 branch is unreachable. Success body = same `JournalEntrySerializer` item as the list. See GAPS. |

Entry item (verified): `correlation_id` (UUID string), `account_id` (UUID string), `signal_snapshot` (object|null; observed keys `symbol, account_id, confidence, signal_type`), `decision_snapshot` (object|null; `symbol, decision, quantity, account_id`), `order_events` (array|null; each `{event_type, event_id, occurred_at, payload}` where payload = raw event payload e.g. `{side, symbol, order_id, quantity, account_id}`), `position_id` (UUID string|null), `outcome` (`"won"|"lost"|"breakeven"|null`), `realized_pnl` (decimal string|null, e.g. `"0.00000000"`), `finalized` (bool), `finalized_at` (ISO|null), `created_at` (**always null**), `updated_at` (**always null** — snapshot dataclass has no such fields).

Filter: `?finalized=true` verified.

SOURCE: `backend/apps/journal/interfaces/api/urls.py`, `views.py`

## Audit — `/api/v1/audit/` (✅ VERIFIED live 2026-08-17)

| Method | Path | Purpose | Verified body |
|---|---|---|---|
| GET | `entries/` | Audit log | **Paginated** `{count, next, previous, results}` (PAGE_SIZE=20); requires `staff`/`owner` role (403 otherwise, verified) |

Entry item (verified): `id` (UUID string), `actor` (`"system"|"user"|"ai"`), `action` (e.g. `accounts.UserLoggedIn`, `rule_engine.RuleFired`, `signals.SignalCreated`, `journal.EntryFinalized`), `target_type` (event prefix, e.g. `signals`, `rule_engine`), `target_id` (UUID string), `metadata` (JSON event payload; for `rule_engine.RuleFired` includes `symbol, rule_id, severity, event_type, occurred_at, trigger_data, analysis_event_id`), `occurred_at` (ISO), `created_at` (ISO).

Logins are audited automatically (`accounts.UserLoggedIn`). `?target_type=` filter verified.

SOURCE: `backend/apps/audit_log/urls.py`

## Rule Engine — `/api/v1/rule-engine/` (✅ VERIFIED live 2026-08-17)

| Method | Path | Purpose | Verified body |
|---|---|---|---|
| GET | `configs/` | List RuleConfigs | **BARE ARRAY** (NOT paginated) of `RuleConfig` items |
| GET | `configs/<rule_id>/` | One RuleConfig | same shape; 404 → Problem detail `{"type":"urn:tradevision:error:rule-config-not-found","title":"Rule config <id> not found","status":404,"instance":"/api/v1/rule-engine/configs/<id>/"}` (no `correlation_id`) |
| GET | `executions/` | List RuleExecutions | **BARE ARRAY** (NOT paginated) of `RuleExecution` items; `?rule_id=` filter verified |

`RuleConfig` item (verified): `{id, rule_id, enabled, parameters, severity_override, created_at, updated_at}`. ⚠ `validated_regimes` is **NOT exposed** by the API — it is stored on the model but the serializer omits it (see GAPS).

`RuleExecution` item (verified): `{id, analysis_event_id, rule_id, symbol, severity, trigger_data, published_event_id, created_at}`. `published_event_id` = the rule-fired event UUID; `id` is unique (multiple rules share the same `analysis_event_id`).

`trigger_data` keys observed per rule:
- `price_movement_v1`: `regime, change_pct, current_price, threshold_pct`
- `volume_spike_v1`: `regime, ratio, volume, avg_volume_20d, threshold_multiplier`
- `breakout_v1`: `regime, bb_upper, bb_upper_break[, resistance_break, resistance_level]`
- `long_momentum_v1`: `regime, setup, vwap, ema_20, volume, stop_loss, stop_loss_basis, change_pct, entry_price, volume_ratio, avg_volume_10d, opening_15m_low, opening_15m_open`
- `high_beta_breakout_v1`: `regime, setup, rsi_14, volume, bb_upper, entry_price, volume_ratio, avg_volume_5d`
- `short_breakdown_v1`: `regime, setup, vwap, rsi_14, volume, direction, entry_price, volume_ratio, avg_volume_10d`

SOURCE: `backend/apps/rule_engine/interfaces/api/views.py`, `urls.py`, `serializers.py`; model in `apps/rule_engine/infrastructure/models.py`

---

## Research / Backtesting — `/api/v1/backtesting/` (✅ all shapes VERIFIED)

### POST `runs/` — create + enqueue a backtest (VERIFIED)
Request (BacktestRunCreateSerializer):
```json
{"symbol":"RELIANCE","timeframe":"15min","range_start":"2024-01-01T00:00:00Z","range_end":"2024-06-01T00:00:00Z","initial_capital":1000000}
```
- `timeframe` optional, default `""`; `initial_capital` optional, default `1000000` (max 20 digits, 8 decimals).
- 400 if `range_end <= range_start`.
Response 201 (VERIFIED, `views.py:69`):
```json
{"run_id":"<uuid>","account_id":"<uuid>","status":"PENDING","symbol":"RELIANCE","timeframe":"15min","range_start":"...","range_end":"..."}
```

### GET `runs/<uuid:run_id>/` — status + full stats (VERIFIED)
200 payload = BacktestRunStatsSerializer fields PLUS `stats`:
```json
{
  "run_id":"...","status":"COMPLETED","account_id":"...","symbol":"...","timeframe":"...",
  "range_start":"...","range_end":"...","failure_reason":"","started_at":"...","completed_at":"...",
  "stats": { /* run_stats, see below */ }
}
```
404 if run not found: `{"detail":"BacktestRun not found"}`.

### POST `walk-forward/` — rolling OOS validation (VERIFIED)
Request (WalkForwardSerializer): `symbol, timeframe?, range_start, range_end, window_size_days(int>=1), step_size_days(int>=1), in_sample_ratio?(default "0.70"), initial_capital?`
Response 200 (VERIFIED, `walk_forward_service.py:191`):
```json
{
  "symbol","timeframe","range_start","range_end","window_size_days","step_size_days",
  "in_sample_ratio":"0.70","total_windows":N,"included_window_count":N,"excluded_window_count":N,
  "windows":[ {"window_index":0,"range_start","range_end","run_id","account_id","status",
               "in_sample_trade_count","out_of_sample_trade_count","in_sample_expectancy",
               "out_of_sample_expectancy","out_of_sample_sharpe_ratio","out_of_sample_win_rate"} ],
  "distribution":{
    "out_of_sample_expectancy": {"count":0,"min":null,"max":null,"median":null,"count_positive":0},
    "out_of_sample_sharpe_ratio": {...},
    "out_of_sample_win_rate": {...}
  }
}
```
`distribution` entries use `min/max/median` as strings, all-`null` when empty; windows below `MIN_TRADES_FOR_DISTRIBUTION=2` OOS trades are excluded.

### POST `edge-validation/` — per-rule empirical edge at two cost levels (VERIFIED)
Request (EdgeValidationSerializer): `symbol, timeframe?, range_start, range_end, window_size_days, step_size_days, in_sample_ratio?(0.70), realistic_commission_rate?(0.0003), realistic_slippage_bps?(5.0), initial_capital?`
Response 200 (VERIFIED, `edge_validation_service.py:290`):
```json
{
  "symbol","timeframe","range_start","range_end","window_size_days","step_size_days",
  "in_sample_ratio","realistic_commission_rate","realistic_slippage_bps","edge_criterion",
  "baseline": { /* full evaluate report at 0 cost */ },
  "realistic_cost": { /* full evaluate report at realistic cost */ },
  "by_rule": {
    "<rule_id>": {"rule_id","baseline_has_edge","realistic_cost_has_edge","flipped",
                  "baseline":{...},"realistic_cost":{...}}
  }
}
```
Each embedded report (`evaluate` return, `edge_validation_service.py:182`): `symbol, timeframe, range_start, range_end, window_size_days, step_size_days, in_sample_ratio, commission_rate, slippage_bps, edge_criterion, single_run, walk_forward, by_rule`. `edge_criterion` is the literal disclosed dict (VERIFIED `edge_validation_service.py:64`): `{"expectancy_greater_than_zero": true, "profit_factor_not_none": true, "profit_factor_greater_than_one": "1.0", "min_trades": 10, "insufficient_data": "has_edge=None when trade_count < min_trades (never False)"}`. Each rule report (`_single_rule_report`): `rule_id, trade_count, win_rate, expectancy, profit_factor, sharpe_ratio, sortino_ratio, max_drawdown_pct, has_edge` where `has_edge` is True/False/None (None = insufficient data, never False).

### POST `cost-sensitivity/` — commission/slippage breakeven sweep (VERIFIED)
Request (CostSensitivitySerializer): `symbol, timeframe?, range_start, range_end, commission_start, commission_end, commission_step, slippage_start, slippage_end, slippage_step, initial_capital?`. Grid limited to `MAX_GRID_POINTS=50` (400 if exceeded). All steps must be positive, end>=start, `range_end>range_start`.
Response 200 (VERIFIED, `cost_sensitivity_service.py:267` + `:336`):
```json
{
  "grid_points_run":N,
  "by_rule":{
    "<rule_id>":{
      "rule_id","expectancy_at_min_cost","expectancy_at_max_cost",
      "breakeven_commission_rate","breakeven_slippage_bps",
      "classification":"BREAKEVEN_FOUND"|"NEVER_PROFITABLE"|"SURVIVES_FULL_RANGE",
      "series":[ {"cost_level":"...","expectancy":"..."} ]
    }
  }
}
```
`breakeven_*` are `null` when classification is `NEVER_PROFITABLE`.

### `run_stats` payload (the `stats` object from GET run detail) — VERIFIED full shape (`services.py:653`)
```json
{
  "status","trade_count","fill_count","win_count","loss_count","risk_rejected_count",
  "gross_profit":"...","gross_loss":"...","total_transaction_costs":"...","total_slippage_impact":"...",
  "net_pnl":"...","win_rate":"...","expectancy":"...","profit_factor":"..."|null,
  "max_drawdown_pct":"...","sharpe_ratio":"..."|null,"sortino_ratio":"..."|null,
  "benchmark_return_pct":"..."|null,"equity_at_completion":"...","available_capital":"...",
  "in_sample": { /* bucket */ },
  "out_of_sample": { /* bucket */ },
  "by_regime": {"<regime>": { /* bucket + metrics */ }},
  "missing_regime_count":0,
  "by_rule": {"<rule_id>": {"rule_id", /* bucket + metrics */ }},
  "unattributed_trade_count":0,
  "trades":[ {"order_id","symbol","side","quantity","entry_price","avg_fill_price","filled_quantity",
              "status","realized_pnl","net_pnl","transaction_cost","created_at"} ]
}
```
Bucket shape (per regime/rule/IS/OOS): `trade_count, win_count, loss_count, gross_profit, gross_loss, total_transaction_costs, net_pnl, win_rate, avg_win, avg_loss, expectancy, profit_factor|null, sharpe_ratio|null, sortino_ratio|null, max_drawdown_pct, max_drawdown_amount, trades[]`.
`ratio*` fields are `null` when there is no valid computation (e.g. empty bucket). All money/ratio values are strings.

---

## Other API Surfaces (endpoints ✅ verified; bodies ✅ where noted)

- `/api/v1/recommendations/`: `GET ""`, `GET <uuid>/`, `POST <uuid>/accept/`, `POST <uuid>/reject/`, `GET <uuid>/explanation/`. SOURCE: `apps/recommendations/interfaces/api/urls.py` — verified: GET `""` → `[]` (list, not paginated)
- `/api/v1/trader-memory/`: `GET entries/`, `GET projections/<strategy_id>/`. SOURCE: `apps/trader_memory/interfaces/api/urls.py` — verified: `entries/` → `[]`
- `/api/v1/signals/`: `GET ""`, `GET <uuid>/`. SOURCE: `apps/signals_engine/interfaces/api/urls.py` — verified: paginated `{count,next,previous,results}`
- `/api/v1/ingestion/`: `GET raw-events/`, webhook paths (POST, token-protected). SOURCE: `apps/ingestion/interfaces/api/urls.py` — verified: `raw-events/` → paginated
- `/api/v1/technical-analysis/`: `webhooks/tradingview/<token>/` (POST). SOURCE: `apps/technical_analysis/interfaces/api/urls.py`
- `/api/v1/pattern-engine/`: `GET historical-vectors/`, `GET runs/`, `GET runs/<uuid>/`. SOURCE: `apps/pattern_engine/interfaces/api/urls.py` — verified: paginated
- `/api/v1/risk-management/`: `GET decisions/`, `GET kill-switch/`, `POST kill-switch/activate/`, `POST kill-switch/deactivate/`. SOURCE: `apps/risk_management/interfaces/api/urls.py` — verified: `decisions/` → `[]` (list), `kill-switch/` → `[]` (list)
- `/api/v1/portfolio/`: `GET ""`, `GET positions/`, `POST fills/`. SOURCE: `apps/portfolio/interfaces/api/urls.py` — verified: `GET ""` → `{account_id, cash, margin_used, equity, available_capital, realized_pnl_today, unrealized_pnl_today}`; `GET positions/` → plain array of `{account_id, symbol, side, quantity, avg_entry_price, opened_at, current_price, unrealized_pnl, exposure}` (NOT paginated). 404 `no-primary-account` if no default `Account` row exists.
- `/api/v1/execution/`: `GET requests/`, `GET orders/`, `GET orders/<uuid>/`. SOURCE: `apps/execution/interfaces/api/urls.py` — verified: `orders/` → paginated
- `/api/v1/watchlist/`: `GET ""`, `POST reorder/`, `GET|DELETE|PATCH <instrument_token>/`. SOURCE: `apps/watchlist/interfaces/api/urls.py` — verified: `GET` requires `?account_id=<uuid>` (400 without); 403 if the account is not owned by the caller; returns array of enriched items
- `/api/v1/pipeline-health/`: `GET ""`. SOURCE: `apps/pipeline_health/interfaces/api/urls.py` — verified: `{heartbeats:[]}`
- `/api/v1/portfolio-reconciliation/`: `GET drift/summary/`, `GET drift/`. SOURCE: `apps/portfolio_reconciliation/interfaces/api/urls.py` — verified: `drift/summary/` → `{classification_breakdown:{}, total_records, last_run_at}`; `drift/` → paginated
- `/api/v1/journal/`: `GET entries/` (requires `?account_id=`, 400 without), `GET entries/<uuid:correlation_id>/`. SOURCE: `apps/journal/interfaces/api/urls.py` — verified 2026-08-17: `entries/` → **bare array** (NOT paginated); `entries/<correlation_id>/` currently always 500s (view bug, see GAPS)
- `/api/v1/audit/`: `GET entries/`. SOURCE: `apps/audit_log/urls.py` — verified: paginated, `staff`/`owner` required
- `/api/v1/rule-engine/`: `GET configs/`, `GET configs/<rule_id>/`, `GET executions/`. SOURCE: `apps/rule_engine/interfaces/api/urls.py` — verified 2026-08-17: `configs/` and `executions/` are **bare arrays** (NOT paginated); configs omit `validated_regimes`

## Endpoint Count

- Mounted root prefixes: 22 total (`backend/config/urls.py`: 20 × `api/v1` + `/admin/` + `/metrics/`).
- Individual routes enumerated above: 67 (exact count across mounted `urls.py` files).
- Live verification completed 2026-08-16/17: every ⚠ endpoint now has a verified status code + body shape (see the tables above), including the previously-unverified Journal, Audit, and Rule Engine bodies (verified live 2026-08-17). Remaining known gaps are documented in `08_GAPS_BLACKLIST_AND_ASSUMPTIONS.md` (notably: trade-export needs a Celery worker/broker; no dedicated equity-curve endpoint; journal detail `entries/<correlation_id>/` always 500s due to a view bug; journal/rule-engine lists are bare arrays, not paginated; `created_at`/`updated_at` always null on journal items; rule-engine configs do not expose `validated_regimes`).