# 04 — API Contract (Verified Endpoints + Response Shapes)

Base URL: `/api/v1`. All responses are JSON. Errors follow `{"error": {code, message, details?}}` (see 01). List endpoints paginate with `{count, next, previous, results}` (PAGE_SIZE=20).
Numeric Decimal fields are serialized as **strings** (`str(...)`), not JSON numbers. Treat them as strings and convert client-side.

Legend: ✅ = exact shape verified in source · ⚠ = endpoint verified, exact body requires verification.

---

## Auth — `/api/v1/auth/` (all ✅ VERIFIED)

| Method | Path | Request | Response |
|---|---|---|---|
| POST | `login/` (alias `token/`) | `{"username","password"}` | 200 `{"access","refresh","user":{...}}`; 401 `{"error":{code,message}}` |
| POST | `refresh/` (alias `token/refresh/`) | `{"refresh"}` | 200 `{"access","refresh"}`; 401 error |
| GET | `me/` | — | ⚠ 403 now (auth gap); `UserSerializer.data` when wired |
| GET | `api-keys/` | — | ⚠ list of own keys; 403 now |
| POST | `api-keys/` | `{"scopes":["..."]}` | ⚠ `{"id","raw_key","scopes",...}` (raw shown once); 403 now |
| DELETE | `api-keys/<uuid:pk>/` | — | 204; 403 now |

SOURCE: `backend/apps/accounts/interfaces/api/views.py`, `urls.py`

---

## Health — `/api/v1/health/` (✅ VERIFIED)

`GET /` liveness; `GET db/`, `cache/`, `celery/`, `eventbus/`, `system/`. Unauthenticated, not throttled.
SOURCE: `backend/apps/health/urls.py`

---

## Dashboard — Trading Core `/api/v1/dashboard/` (shapes ✅ from serializers)

| Method | Path | Response shape (serializer) |
|---|---|---|
| GET | `home/summary/` | `DashboardHomeSummarySerializer`: `account_id, open_positions_count, open_orders_count, today_realized_pnl, today_unrealized_pnl, active_alerts_count, broker_connection_status, market_session_status, last_updated_at` |
| GET | `portfolio/composition/` | `account_id, total_market_value, total_cost_basis, cash_balance` (+ holdings) |
| GET | `portfolio/holdings/<symbol>/` | `HoldingSerializer`: `account_id, symbol, quantity, avg_cost, cost_basis, market_value, allocation_pct, unrealized_pnl, opened_at` |
| GET | `positions/live/` | list of `PositionSnapshotSerializer`: `position_id, account_id, symbol, side, ...` |
| GET | `positions/live/<position_id>/` | single position snapshot |
| GET | `orders/` | list of `OrderSnapshotSerializer` |
| GET | `orders/<order_id>/` | single order snapshot |
| GET | `trades/history/` | list of `TradeRecordSerializer` |
| GET | `trades/history/export/` | ⚠ creates export job; `ExportRequestSerializer`/`ExportJobSerializer` |
| GET | `trades/history/export/<export_id>/` | ⚠ export status |
| GET | `trades/open/` | open trades list |
| GET | `trades/closed/` | closed trades list |

SOURCE: `backend/apps/dashboard/interfaces/api/trading_core/urls.py`, `serializers.py`, `views.py`

Note: the exact JSON key set beyond the listed serializer fields was not fully traced for every view — treat the listed keys as canonical and render unknown keys defensively (ignore extras, show `--` for missing).

---

## Dashboard — Analytics & Risk `/api/v1/dashboard/accounts/<account_id>/` (✅ endpoints, ⚠ bodies)

| Method | Path | Purpose |
|---|---|---|
| GET | `pnl` | PnL analytics |
| GET | `pnl/daily` | Daily rollup (for equity/returns chart) |
| GET | `performance` | Performance metrics |
| GET | `risk` | Risk summary |

SOURCE: `backend/apps/dashboard/interfaces/api/analytics_risk/urls.py`, `views.py`

---

## Journal — `/api/v1/journal/` (✅ endpoints, ⚠ bodies)

`GET entries/`, `GET entries/<uuid:correlation_id>/`.
SOURCE: `backend/apps/journal/interfaces/api/urls.py`

## Audit — `/api/v1/audit/` (✅ endpoints, ⚠ bodies)

`GET entries/`. SOURCE: `backend/apps/audit_log/urls.py`

## Rule Engine — `/api/v1/rule-engine/` (✅ endpoints, ⚠ bodies)

| Method | Path | Purpose |
|---|---|---|
| GET | `configs/` | List RuleConfigs (rule_id, enabled, parameters, severity_override, validated_regimes) |
| GET | `configs/<rule_id>/` | One RuleConfig |
| GET | `executions/` | List RuleExecutions (analysis_event_id, rule_id, symbol, severity, trigger_data) |

SOURCE: `backend/apps/rule_engine/interfaces/api/views.py`, `urls.py`; model in `apps/rule_engine/infrastructure/models.py`

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

## Other API Surfaces (endpoints ✅ verified; bodies ⚠)

- `/api/v1/recommendations/`: `GET ""`, `GET <uuid>/`, `POST <uuid>/accept/`, `POST <uuid>/reject/`, `GET <uuid>/explanation/`. SOURCE: `apps/recommendations/interfaces/api/urls.py`
- `/api/v1/trader-memory/`: `GET entries/`, `GET projections/<strategy_id>/`. SOURCE: `apps/trader_memory/interfaces/api/urls.py`
- `/api/v1/signals/`: `GET ""`, `GET <uuid>/`. SOURCE: `apps/signals_engine/interfaces/api/urls.py`
- `/api/v1/ingestion/`: `GET raw-events/`, webhook paths (POST, token-protected). SOURCE: `apps/ingestion/interfaces/api/urls.py`
- `/api/v1/technical-analysis/`: `webhooks/tradingview/<token>/` (POST). SOURCE: `apps/technical_analysis/interfaces/api/urls.py`
- `/api/v1/pattern-engine/`: `GET historical-vectors/`, `GET runs/`, `GET runs/<uuid>/`. SOURCE: `apps/pattern_engine/interfaces/api/urls.py`
- `/api/v1/risk-management/`: `GET decisions/`, `GET kill-switch/`, `POST kill-switch/activate/`, `POST kill-switch/deactivate/`. SOURCE: `apps/risk_management/interfaces/api/urls.py`
- `/api/v1/portfolio/`: `GET ""`, `GET positions/`, `POST fills/`. SOURCE: `apps/portfolio/interfaces/api/urls.py`
- `/api/v1/execution/`: `GET requests/`, `GET orders/`, `GET orders/<uuid>/`. SOURCE: `apps/execution/interfaces/api/urls.py`
- `/api/v1/watchlist/`: `GET ""`, `POST reorder/`, `GET|DELETE|PATCH <instrument_token>/`. SOURCE: `apps/watchlist/interfaces/api/urls.py`
- `/api/v1/pipeline-health/`: `GET ""`. SOURCE: `apps/pipeline_health/interfaces/api/urls.py`
- `/api/v1/portfolio-reconciliation/`: `GET drift/summary/`, `GET drift/`. SOURCE: `apps/portfolio_reconciliation/interfaces/api/urls.py`

## Endpoint Count

- Mounted root prefixes: 22 total (`backend/config/urls.py`: 20 × `api/v1` + `/admin/` + `/metrics/`).
- Individual routes enumerated above: 67 (exact count across mounted `urls.py` files).
- Exact response bodies for the ⚠ endpoints were not fully traced — verify against the corresponding view/serializer before rendering field-by-field.