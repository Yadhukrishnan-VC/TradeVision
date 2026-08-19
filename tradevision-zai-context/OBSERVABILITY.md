# Observability audit

> Workstream WS7 — tests for the existing health-check endpoints and the
> correlation-ID middleware (previously untested).

## What already existed

The `apps/health` app was well-built but had an empty `tests/` directory:

- `GET /api/v1/health/` — liveness (200, version, uptime_seconds)
- `GET /api/v1/health/db/` — PostgreSQL `ensure_connection()` probe
- `GET /api/v1/health/cache/` — cache write/read round-trip
- `GET /api/v1/health/celery/` — Celery `inspect().ping()` broadcast (degraded, not unhealthy, when no workers)
- `GET /api/v1/health/eventbus/` — Redis Streams publish/consume round-trip
- `GET /api/v1/health/system/` — aggregate (worst-case of the above; celery degraded → 200, anything unhealthy → 503)

All unauthenticated + unthrottled by design so Docker `HEALTHCHECK` and load
balancers can reach them without credentials.

`apps/common/infrastructure/middleware.py` already implements
`CorrelationIdMiddleware`: reads `X-Correlation-ID` (or generates a UUID),
sets `request.correlation_id`, loads it into the structured-logging context,
and stamps the response with the same header. Registered in `MIDDLEWARE`.

## Tests added

- `apps/health/tests/test_health.py` (10 tests):
  - liveness returns 200 with `status`/`version`/`uptime_seconds`
  - DB probe healthy (real PostgreSQL in the test env)
  - cache probe healthy under a working `LocMemCache`, and 503 `unhealthy`
    under `DummyCache` (the failure path — tests `CACHES` in `testing.py`)
  - Celery probe: degraded 503 with no workers, healthy 200 with a worker,
    degraded 503 when the ping raises — Celery broadcast mocked (it is
    non-deterministic / slow against the real broker)
  - EventBus probe healthy against the real Redis (local + CI redis:7 service)
  - system probe: `degraded` 200 when only Celery is down; `unhealthy` 503
    when the cache fails
- `apps/common/tests/test_middleware.py` (3 tests): generates a valid UUID4
  when no header is sent, echoes an inbound header, and issues distinct IDs
  across requests.

## Contract notes

- Celery degradation maps to HTTP **503** on the single-check endpoint but
  only `degraded`→**200** inside the aggregate endpoint. That asymmetry is
  intentional in the source (`views.py`); it is preserved by the tests.
- The cache probe depends on the configured cache backend; the failure-path
  test pins the `DummyCache` from `testing.py` so it is deterministic.

## Run

```bash
cd backend
.venv/bin/pytest apps/health apps/common/tests/test_middleware.py -q   # 13 passed
```