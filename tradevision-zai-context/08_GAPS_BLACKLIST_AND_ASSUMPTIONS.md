# 08 — Backend Gaps, API Blacklist, and Assumptions

## Backend Gaps (things the UI needs that the backend does not provide)

These are **verified absence** items. Do NOT build UI that depends on them, and do NOT "fix" them in the backend. Render empty/`--` states.

### P1 — No market-data OHLC HTTP API

- Candle/Instrument models exist, and candles are replayed inside backtests, but **no endpoint exposes candles or instruments** over HTTP. A symbol search box or a live price chart has no backend source.
- SOURCE: `backend/config/urls.py` (market_data is NOT mounted), `backend/apps/market_data/infrastructure/models.py`
- UI impact: no live/detailed price charts as a standalone feature. (Watchlist references instruments by `instrument_token` but the watchlist API does not return instrument metadata over the dashboards' contracts.)

### P2 — No trade-export / CSV file endpoint contract verified

- `trades/history/export/` and `.../export/<id>/` exist in trading_core; the exact response (file vs job metadata) is ⚠ not verified. Build defensively against `ExportJobSerializer` fields; prefer an export-status UI over a raw file download.

### P3 — Equity-curve series is not a top-level field

- `run_stats` returns `equity_at_completion` (scalar) and per-bucket `equity_curve` arrays for in_sample/out_of_sample/by_regime/by_rule, but not one merged daily equity curve. Build merged curve from `trades[].net_pnl` cumulative or use the IS/OOS curves.

### P4 — No drawdown / returns series

- Only `max_drawdown_pct` (scalar) is returned; no drawdown-over-time series. `returns[]` arrays exist per bucket for distribution, but no date-indexed daily series is exposed. Do not fabricate.

### P5 — Long-running synchronous research endpoints

- Walk-forward / edge-validation / cost-sensitivity run synchronously in the request thread and require `CELERY_TASK_ALWAYS_EAGER=True`. Under a normal worker setup these will block/timeout. UI must tolerate long/indeterminate responses and network timeouts.

### P6 — No pagination params documented on research endpoints

- Research POST endpoints return bare objects (not the paginated envelope). Do not send `?page=` to them.

### P7 — Dead legacy auth code

- `CustomTokenObtainPairView`/Serializer exist in `apps/accounts/views.py`, `serializers.py`, `urls.py` and are **not** mounted. Do not call any `/api/v1/accounts/...` path.

### P8 — Unmounted apps

- Apps like `notifications`, `alerts`, `broker_connectors`, `market_session` may exist as code but are not in `config/urls.py` — no HTTP surface. Do not build UI for them.

## API Blacklist and Rules of Engagement

### Blacklist (never call from the frontend)

| Path | Reason |
|---|---|
| `/api/v1/accounts/...` | Legacy auth views not mounted in root urls (`backend/config/urls.py`). 404. |
| `/api/v1/ingestion/webhooks/*`, `/api/v1/technical-analysis/webhooks/*` | Provider-facing, token-protected. Not for the dashboard UI. |
| `/metrics/` | Prometheus scrape endpoint — server/infra only. |
| `/admin/` | Django admin — operator, not the SPA. |
| `POST /api/v1/portfolio/fills/` | Record-fill is a back-office write; guard heavily or omit from UI (owner/staff). |
| Any `PATCH/PUT` on `rule-engine/configs/` | Only `GET` list/detail + executions are defined. No config-write contract exists. |

### Rules of engagement

1. **Read-first.** The overwhelming majority of the API surface is read-only (dashboard, audit, journal, health, pipeline, rules configs/executions, memory projections). Build read views first.
2. **Writes are limited to**: login/refresh, api-keys management (⚠), creating backtest runs, walk-forward/edge/cost POSTs, watchlist reorder, recommendation accept/reject, kill-switch activate/deactivate, portfolio fill record. Every write needs a user-confirmed action and must surface the error envelope on failure.
3. **Research POSTs are expensive and synchronous** (walk-forward/edge/cost) — one submission at a time, no auto-retry, show progress.
4. **Backtest runs are async** — poll `GET /runs/:id/` (status PENDING→RUNNING→COMPLETED/FAILED). Stop polling on COMPLETED/FAILED or after a generous timeout; render `failure_reason` on FAILED.
5. **Never send pagination params to research/analysis POST endpoints** — they return bare objects.
6. **Never read query params that aren't in the contract** (e.g. `?page=` is fine for list endpoints via the envelope's `next/previous`; do not invent filters like `?symbol=` on list endpoints).
7. **Authentication**: attach `Authorization: Bearer <access>` to every request; on 401 → refresh → retry once → else redirect to `/login`.
8. **Idempotency of display**: if two sources report the same entity (run stats vs run detail), prefer the most recent fetch; never merge across sources to invent a field.
9. **Numbers as strings**: keep them as strings until formatting; never `Number()` a possibly-`null` value (NaN bugs).
10. **Unknown response fields**: ignore silently; missing fields render `--`. This keeps the UI robust to the ⚠ endpoints being richer/different than documented.

## Assumptions and Uncertainties

Everything marked VERIFIED was read directly from source. Everything else is provisional.

### Verified beyond doubt (high confidence)

- REST_FRAMEWORK config incl. authentication classes, pagination, exception handler. (`backend/config/settings/base.py`)
- All root URL mounts + all enumerated endpoint paths + their view classes. (`backend/config/urls.py`, each app `urls.py`)
- Login/refresh request/response contracts incl. error codes. (`backend/apps/accounts/interfaces/api/views.py`)
- Backtest run create/detail payloads, `run_stats` full shape, walk-forward/edge/cost request+response shapes. (`backend/apps/backtesting/**`)
- All 8 rule IDs. (`backend/apps/rule_engine/domain/rules/*.py`)
- RuleConfig/RuleExecution/User/Account/Instrument/Candle/TASnapshot/BacktestRun field sets. (model files)
- ADR-029 gate semantics + validated_regimes storage. (`rule_validation_service.py`, migration)
- Error envelope format. (`drf_exception_handler.py`)
- Frontend scaffold contents (package.json, App.tsx). (`frontend/`)
- Frontend response-shape serializers for trading_core dashboard (serializer field names).

### NOT VERIFIED / requires verification before rendering field-by-field (medium confidence)

- Exact JSON key sets returned by: `/auth/me/`, `/auth/api-keys/`, `/dashboard/accounts/:id/pnl*`, `/performance`, `/risk`, `/journal/entries/`, `/audit/entries/`, `/rule-engine/configs*`, `/rule-engine/executions/`, `/recommendations/*`, `/signals/*`, `/trader-memory/*`, `/pattern-engine/*`, `/portfolio/*`, `/risk-management/*`, `/pipeline-health/`, `/portfolio-reconciliation/*`, `/watchlist/*`, `/execution/*`, `/ingestion/raw-events/`, trade export.
  - Strategy: build typed interfaces from the ⚠ documented fields, render defensively (ignore unknown, `--` for missing), and adjust once live payloads are observed.
- Whether the top-level `run_stats` includes an `equity_curve` key in the final return (the top-level return in `services.py:653` lists `equity_at_completion` and per-bucket curves, but a merged curve key was NOT seen — do not assume it exists; build from `trades[].net_pnl` cumulative or bucket arrays).
- `edge_criterion` / `EDGE_CRITERION` value: VERIFIED and quoted in `04_API_CONTRACT.md` (`expectancy_greater_than_zero`, `profit_factor_greater_than_one=1.0`, `min_trades=10`).
- Cost-sensitivity classification constants: VERIFIED exact spellings — `BREAKEVEN_FOUND`, `NEVER_PROFITABLE`, `SURVIVES_FULL_RANGE` (`cost_sensitivity_service.py:52-54`).
- `CELERY_TASK_ALWAYS_EAGER` requirement: stated in view/service docstrings (VERIFIED as documented intent); whether a live deployment enables it is an ops fact, not verified.

### Assumptions (documented choices, may be wrong)

- The trading_core dashboard serializers' field lists reflect actual view output (serializer `data` is serialized directly in views — `return Response(serializer.data)` — so this is high-confidence, but ordering/extra computed fields were not traced into every view).
- Regime strings in `by_regime` and `trigger_data["regime"]` are arbitrary — UI must not assume a fixed set.
- `watchlist` item paths use `<int:instrument_token>` (instrument_token is BigInteger) — the URL param is an integer.
- Account context: the SPA assumes a "current account" concept; the default account id is expected from `/auth/me/` (⚠) — until then, account-driven pages use ids passed in the route/from run responses.

### Explicit non-goals / unresolved

- No live backend was queried during this audit; all contracts are source-derived. The ⚠ endpoint bodies are the main uncertainty.
- Broker/provider connectivity status (`broker_connection_status`, `market_session_status`) fields exist in serializers but the live values/source were not verified.
- The number of lines/figures in this package is small by design (compact, actionable); the repo is ~599 MB and this package is a few KB.