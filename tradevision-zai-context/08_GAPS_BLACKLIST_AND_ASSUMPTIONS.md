# 08 — Backend Gaps, API Blacklist, and Assumptions

## Backend Gaps (things the UI needs that the backend does not provide)

These are **verified absence** items. Do NOT build UI that depends on them, and do NOT "fix" them in the backend. Render empty/`--` states.

### P1 — No market-data OHLC HTTP API

- Candle/Instrument models exist, and candles are replayed inside backtests, but **no endpoint exposes candles or instruments** over HTTP. A symbol search box or a live price chart has no backend source.
- SOURCE: `backend/config/urls.py` (market_data is NOT mounted), `backend/apps/market_data/infrastructure/models.py`
- UI impact: no live/detailed price charts as a standalone feature. (Watchlist references instruments by `instrument_token` but the watchlist API does not return instrument metadata over the dashboards' contracts.)

### P2 — Trade export endpoint requires a live Celery broker/worker

- `POST trades/history/export/` is verified to return 202 + `ExportJobSerializer` when Celery runs eagerly (`CELERY_TASK_ALWAYS_EAGER=True`, test settings). Under staging settings the request fails with 500 (`AttributeError: 'str' object has no attribute 'name'`) because `CELERY_TASK_QUEUES` is a plain string list, which breaks the Celery 5.6 AMQP router, and because no broker/worker is running.
- UI impact: keep the export-status UI defensive; if the POST fails, surface the error envelope. Do not assume a file download URL will be populated. (Ops item — not fixed in this batch; infra is a non-goal.)

### P3 — Equity-curve series is not a top-level field

- `run_stats` returns `equity_at_completion` (scalar) and per-bucket `equity_curve` arrays for in_sample/out_of_sample/by_regime/by_rule, but not one merged daily equity curve. Build merged curve from `trades[].net_pnl` cumulative or use the IS/OOS curves. There is no dedicated `/analytics/.../equity/curve/` endpoint — the dashboard equity chart is sourced from `pnl/daily` (`total_pnl` cumulative).

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

- Live verification completed 2026-08-16/17 against the staging backend (seeded account + dashboard read-model rows + journal/audit/rule-engine seed rows). The following bodies are now **VERIFIED live** and recorded in `04_API_CONTRACT.md`: `/auth/me/`, `/auth/api-keys/`, `/dashboard/home/summary/`, `/dashboard/portfolio/composition/`, `/dashboard/positions/live/`, `/dashboard/orders/`, `/dashboard/trades/{history,open,closed}/`, `/dashboard/accounts/:id/pnl`, `/pnl/daily` (array + date-range params), `/performance`, `/risk`, `/portfolio/` (capital snapshot), `/portfolio/positions/` (plain array), `/watchlist/?account_id=`, `/risk-management/{decisions,kill-switch}/`, `/pipeline-health/`, `/portfolio-reconciliation/drift/{summary,}/`, `/recommendations/`, `/signals/`, `/trader-memory/entries/`, `/ingestion/raw-events/`, `/execution/orders/`, `/audit/entries/` (paginated; `staff`/`owner` required), `/journal/entries/` (bare array; `?account_id=` required, 400 without), `/rule-engine/configs/` + `/rule-engine/configs/<rule_id>/` + `/rule-engine/executions/` (bare arrays; `trigger_data` per-rule keys recorded).
- Still ⚠ (empty-data only, shape not exercised with rows): trade-export status (requires Celery), watchlist item GET/DELETE/PATCH, pattern-engine run/historical-vector item bodies.
- Whether the top-level `run_stats` includes an `equity_curve` key in the final return (the top-level return in `services.py:653` lists `equity_at_completion` and per-bucket curves, but a merged curve key was NOT seen — do not assume it exists; build from `trades[].net_pnl` cumulative or bucket arrays).
- `edge_criterion` / `EDGE_CRITERION` value: VERIFIED and quoted in `04_API_CONTRACT.md` (`expectancy_greater_than_zero`, `profit_factor_greater_than_one=1.0`, `min_trades=10`).
- Cost-sensitivity classification constants: VERIFIED exact spellings — `BREAKEVEN_FOUND`, `NEVER_PROFITABLE`, `SURVIVES_FULL_RANGE` (`cost_sensitivity_service.py:52-54`).
- `CELERY_TASK_ALWAYS_EAGER` requirement: stated in view/service docstrings (VERIFIED as documented intent); whether a live deployment enables it is an ops fact, not verified.

### Assumptions (documented choices, may be wrong)

- The trading_core dashboard serializers' field lists reflect actual view output (serializer `data` is serialized directly in views — `return Response(serializer.data)` — so this is high-confidence, but ordering/extra computed fields were not traced into every view).
- Regime strings in `by_regime` and `trigger_data["regime"]` are arbitrary — UI must not assume a fixed set.
- `watchlist` item paths use `<int:instrument_token>` (instrument_token is BigInteger) — the URL param is an integer.
- Account context: the SPA assumes a "current account" concept. Verified live: dashboard/analytics views resolve `account_id = request.user.id` (the User's UUID, not a separate Account table id), and `/auth/me/` returns that `id`. Portfolio/Watchlist use a separate `Account` model (`owner` FK); portfolio resolves the primary account via `Account.objects.filter(is_default=True)` and 404s (`no-primary-account`) if none exists. Seed/ensure a default `Account` row owned by the user before calling `/portfolio/`, `/portfolio/positions/`, or `/watchlist/?account_id=`.

### Explicit non-goals / unresolved

- No live backend was queried during this audit; all contracts are source-derived. The ⚠ endpoint bodies are the main uncertainty.
- Broker/provider connectivity status (`broker_connection_status`, `market_session_status`) fields exist in serializers but the live values/source were not verified.
- The number of lines/figures in this package is small by design (compact, actionable); the repo is ~599 MB and this package is a few KB.
- **New finding (2026-08-16): dashboard read-model `side` column is `CharField(max_length=4)` but the domain `Side` enum includes `"SHORT"` (5 chars) — persisting a SHORT row raises `StringDataRightTruncation` (`dashboard_positionsnapshot`/`dashboard_ordersnapshot`/`dashboard_traderecord`). Needs a schema change + migration; left as a documented gap (schema/migration work, not fixed in this batch).**
- **New finding (2026-08-16): dashboard app migrations are undiscoverable** — migration modules live under `apps/dashboard/infrastructure/{trading_core,analytics_risk}/migrations/` but the `dashboard` app label resolves migrations to `apps/dashboard/migrations/` (does not exist), so `showmigrations dashboard` reports `(no migrations)` and the app was treated as unmigrated. Tables were created via `migrate --run-syncdb` for live verification. This is a pre-existing architecture mismatch (D1/D2 split), not fixed in this batch.
- **New finding (2026-08-17): journal detail `GET entries/<uuid:correlation_id>/` ALWAYS 500s** — `backend/apps/journal/interfaces/api/views.py:37` calls `uuid.UUID(correlation_id)` on a value the `<uuid:>` route already converted to a `UUID`, raising `AttributeError: 'UUID' object has no attribute 'replace'`. The 404 branch is unreachable. Success body is the same `JournalEntrySerializer` item as the list (verified shape); the view bug is the only blocker. Not fixed in this batch (interface-layer bug; filed for a follow-up).
- **New finding (2026-08-17): journal items always return `created_at: null` / `updated_at: null`** — `JournalEntrySnapshot` dataclass has no such fields, so the serializer emits nulls. Frontend renders `finalized_at` (and `--` fallback) for the time column.
- **New finding (2026-08-17): rule-engine configs do not expose `validated_regimes`** — the `RuleConfigSerializer` omits it even though the model stores it. ADR-029 gate statuses are DB/ORM-only via this endpoint; the configs API returns `{id, rule_id, enabled, parameters, severity_override, created_at, updated_at}`. Frontend renders `—` for the gate column.