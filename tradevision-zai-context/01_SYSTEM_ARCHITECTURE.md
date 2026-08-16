# 01 — System Architecture

## Request → Response Flow (API Layer)

1. All JSON APIs are under `/api/v1/...`; Django admin under `/admin/`; Prometheus metrics under `/metrics/`.
   SOURCE: `backend/config/urls.py`
2. DRF settings (VERIFIED): `DEFAULT_RENDERER=JSONRenderer`, `DEFAULT_PARSER=JSONParser`, `DEFAULT_PERMISSION=IsAuthenticated`, **`DEFAULT_AUTHENTICATION_CLASSES=[]` (empty)** — see `03_AUTHENTICATION.md` for the critical consequence.
   SOURCE: `backend/config/settings/base.py:191`
3. Pagination: `PageNumberPagination`, `PAGE_SIZE=20`, response envelope `{count, next, previous, results}` for list endpoints.
   SOURCE: `backend/config/settings/base.py:197`
4. Errors: DRF's default handler first, then a custom handler maps domain exceptions to `{"error": {"code": ..., "message": ..., "details": ...}}`:
   - ValidationError → 400, PermissionDeniedError → 403, NotFoundError → 404, ConcurrencyError → 409, DomainError → 400.
   SOURCE: `backend/apps/common/infrastructure/drf_exception_handler.py`

## Django Apps (36)

Root URL wiring (VERIFIED) — `backend/config/urls.py`:

| Prefix | App | Notes |
|---|---|---|
| `/api/v1/auth/` | accounts | login/refresh/me/api-keys |
| `/api/v1/health/` | health | liveness, db, cache, celery, eventbus, system |
| `/api/v1/dashboard/` | dashboard.trading_core | home summary, portfolio composition, positions, orders, trades, export |
| `/api/v1/dashboard/` | dashboard.analytics_risk | pnl, pnl/daily, performance, risk per account |
| `/api/v1/journal/` | journal | entries |
| `/api/v1/audit/` | audit_log | entries |
| `/api/v1/rule-engine/` | rule_engine | configs, executions |
| `/api/v1/recommendations/` | recommendations | list/detail/accept/reject/explanation |
| `/api/v1/trader-memory/` | trader_memory | entries, projections |
| `/api/v1/signals/` | signals_engine | signal list/detail |
| `/api/v1/ingestion/` | ingestion | TradingView + Chartink webhooks, raw-events |
| `/api/v1/technical-analysis/` | technical_analysis | TradingView TA webhook |
| `/api/v1/pattern-engine/` | pattern_engine | historical-vectors, runs |
| `/api/v1/risk-management/` | risk_management | decisions, kill-switch |
| `/api/v1/portfolio/` | portfolio | summary, positions, fills |
| `/api/v1/execution/` | execution | requests, orders (read-only) |
| `/api/v1/backtesting/` | backtesting | runs, walk-forward, cost-sensitivity, edge-validation |
| `/api/v1/watchlist/` | watchlist | list, reorder, item |
| `/api/v1/pipeline-health/` | pipeline_health | pipeline health + staleness |
| `/api/v1/portfolio-reconciliation/` | portfolio_reconciliation | drift summary, drift list |

Other apps exist in the codebase (e.g. `broker_connectors`, `notifications`, `alerts`) but are **not mounted** in the root URL config (NO URL in `backend/config/urls.py`). The UI cannot call them over HTTP.

## Data Flow — Live Trading Pipeline

1. Webhook hits `ingestion` or `technical_analysis` (URL contains a per-provider token) → raw payload stored → domain event published on the event bus.
   SOURCE: `backend/apps/ingestion/interfaces/api/urls.py`, `backend/apps/technical_analysis/interfaces/api/urls.py`
2. Rule engine consumes events; for each enabled `RuleConfig` whose `rule_id` matches, it evaluates the rule against `trigger_data`. ADR-029 adds a go/no-go gate: the rule only fires if its `validated_regimes` for the current `regime` == `"GO"`.
   SOURCE: `backend/apps/rule_engine/`, `backend/apps/backtesting/application/rule_validation_service.py`
3. Firing publishes events that the execution engine turns into orders on a per-account paper broker (FULL_FILL, simulated time via contextvars).
   SOURCE: `backend/apps/execution/application/execution_engine.py`, `backend/apps/execution/infrastructure/brokers/paper_broker.py`

## Backtesting Data Flow (Research)

`POST /api/v1/backtesting/runs/` creates an isolated `Account` + `BacktestRun` and enqueues Celery task `run_backtest` (analytics queue). The task replays candles for `[range_start, range_end]`, executes rules, produces fills, and writes `run_stats` back. `GET /api/v1/backtesting/runs/<id>/` returns status + full statistics.
SOURCE: `backend/apps/backtesting/interfaces/api/views.py`

Walk-forward / edge-validation / cost-sensitivity run **synchronously** in the request thread and require `CELERY_TASK_ALWAYS_EAGER=True` (simulated-time contextvars do not cross Celery worker processes).
SOURCE: `backend/apps/backtesting/interfaces/api/views.py:99` (view docstrings)

## Concurrency & Time

- Background work via Celery, broker = Redis (`CELERY_BROKER_URL`, default `redis://localhost:6379/0`).
- SOURCE: `backend/config/settings/base.py:216`
- All timestamps are timezone-aware; backtest date ranges are passed as ISO-8601 datetimes.