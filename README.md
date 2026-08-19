# TradeVision AI

AI-assisted equity trading research platform. Django REST backend with
Channels (WebSocket) + Celery, a React/Vite frontend, PostgreSQL
(TimescaleDB) via PgBouncer, and Redis as broker/cache. The stack is
containerised with Docker Compose and developed against the same
infrastructure used in production.

This guide covers **local development**. For architecture, API, and
production operations see `docs/architecture/`, `docs/api/`, and
`docs/operations/` respectively.

---

## Prerequisites

- **Docker** with the **Compose plugin** (v2). Check with
  `docker compose version`.
- **Python 3.11+** only if you want to run the test suite directly on the
  host (the normal path is the Dockerized stack, see below).
- The backend, frontend, and Celery worker images are built from the repo
  on first `up`, so an internet connection is needed for the initial build.

## 1. Environment configuration

Copy the environment template into the location Compose reads it:

```bash
cp .env.example infra/.env
```

Compose resolves `env_file: .env` **relative to the compose file**, i.e.
`infra/.env`. The repo's root `.env` is unrelated to Compose and is not
used by the stack.

The template ships with **safe development defaults** for every variable
that the stack needs to boot: database credentials, Redis URLs, Django
settings module, `MARKET_DATA_PROVIDER=mock`, `AI_PROVIDER=gemini`, etc.
No secrets are required to bring the stack up.

Variables that genuinely matter before first `up`:

| Variable | Status | Notes |
| --- | --- | --- |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | required | Must match between Postgres and PgBouncer sections; defaults are safe for local dev |
| `DJANGO_SECRET_KEY` | safe default | `change-me-to-a-long-random-string-in-production` — fine locally, must change in production |
| `JWT_SECRET_KEY` | safe default | as above |
| `MARKET_DATA_PROVIDER` | default `mock` | Leave as `mock` for local dev; see [Zerodha](#6-optional-zerodha-integration) |
| AI provider keys | optional | Only the active `AI_PROVIDER` needs a real key; leave others blank for local dev |

`infra/.env` is git-ignored (`.gitignore`). Never commit real secrets to it.

## 2. Bring up the stack

The full stack (Postgres, PgBouncer, Redis, backend, three Celery
workers, Celery Beat, frontend, Nginx, and — in dev — Flower) is defined
in `infra/docker-compose.yml`. The **dev overlay**
`infra/docker-compose.dev.yml` is the intended local entry point: it
mounts source for hot-reload, sets `config.settings.development`, and
exposes the host ports you need (`8000` backend, `5173` frontend, `5432`
Postgres, `6379` Redis, `6432` PgBouncer, `5555` Flower).

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml up -d
```

- Build the first time with `... up -d --build` if you changed the
  Dockerfiles or `requirements`.
- The **backend entrypoint** (`infra/scripts/entrypoint.backend.sh`)
  waits for Postgres and Redis, runs Django system checks, and applies
  **database migrations automatically** (`python manage.py migrate
  --no-input`) before Daphne starts. You do not normally need to run
  migrations by hand.
- Tear down with `docker compose -f infra/docker-compose.yml -f
  infra/docker-compose.dev.yml down` (add `-v` to also remove the
  Postgres/Redis data volumes).

> **Fixed — PgBouncer image was unavailable.**
> The `pgbouncer` service previously pinned `bitnami/pgbouncer:1.23.1`,
> which Bitnami migrated off Docker Hub (the tag no longer resolves). The
> service now uses the maintained `edoburu/pgbouncer` image with the same
> transaction-pooling configuration and a `psql`-based health check, so the
> full stack comes up cleanly. Supporting fixes landed in the same pass:
> the dev overlay's source mounts now point at `../backend`/`../frontend`
> (they silently resolved to empty `infra/backend`/`infra/frontend`), `daphne`
> is declared in `requirements/base.txt` (the container runs it but never
> installed it), `CELERY_TASK_QUEUES` uses `kombu.Queue` objects (celery
> 5.6 crashes on a bare string list once a worker starts with `--queues`),
> the worker/nginx/flower health checks were corrected, and the dev DB is
> named `tradevision_dev_db` to satisfy the `config.E002` dev-DB naming rule.
> A dev-only Adminer service is available at `http://localhost:8080`
> (server `postgres`, user/password/db from `infra/.env`).

## 3. Health checks

Every service ships a Docker health check (see
`infra/docker-compose.yml`); `docker compose ps` shows `healthy` once a
service has passed its `start_period`.

For an end-to-end confirmation once the backend is up:

```bash
# Backend liveness (direct)
curl http://localhost:8000/api/v1/health/

# Through Nginx reverse proxy
curl http://localhost/api/v1/health/

# Deeper probes (DB, Redis cache, Celery, EventBus, aggregate)
curl http://localhost:8000/api/v1/health/db/
curl http://localhost:8000/api/v1/health/cache/
curl http://localhost:8000/api/v1/health/celery/
curl http://localhost:8000/api/v1/health/eventbus/
curl http://localhost:8000/api/v1/health/system/
```

The health endpoints are unauthenticated and return `200` when healthy
(or degraded) and `503` when a critical dependency is down. Frontend:
`http://localhost:5173` (Vite, with HMR). Celery task monitoring:
`http://localhost:5555` (Flower, default `admin` / `tradevision`).

## 4. Database migrations

Migrations are applied automatically by the backend entrypoint on every
`up` (idempotent). To run them explicitly inside a running container:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml exec backend python manage.py migrate
```

If you change models, create a migration with:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml exec backend python manage.py makemigrations <app>
```

## 5. Seed data

There is **no automated seed step** wired into the compose entrypoint.
One idempotent helper exists:

- `apps/common/management/commands/seed_admin.py` — creates a Django
  superuser from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (defaults
  `admin@tradevision.ai` / `changeme123`), skipping if it already
  exists.

The command derives `username` from the email local-part (falling back to
`admin` with a numeric suffix if taken), so it runs cleanly:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml exec backend python manage.py seed_admin
```

Alternatively, create a superuser interactively:

```bash
docker compose -f infra/docker-compose.yml -f infra/docker-compose.dev.yml exec backend python manage.py createsuperuser --username admin --email admin@tradevision.ai
```

## 6. Running the test suite

`pytest.ini` selects `config.settings.testing`, which targets a real
PostgreSQL database (`tradevision_test`) — never SQLite — and talks to a
real Redis. The tests are run **against the Dockerized Postgres and
Redis**, exactly as in CI.

Because `config.settings.base` resolves the DB host from
`DATABASE_URL` / `POSTGRES_*` (defaulting to `localhost:5432`), running
the suite on the host requires the data tier to be up and the host ports
mapped (the dev overlay provides `5432` and `6379`):

```bash
# from infra/ — bring up at least the data tier
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis

# from backend/
cd ../backend
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=tradevision
export POSTGRES_PASSWORD=tradevision_password
export POSTGRES_DB=tradevision_db
export REDIS_URL=redis://localhost:6379/0
python -m pytest -p no:cacheprovider
```

Notes:

- Use the project's virtualenv (`.venv/bin/python`) if you are on the
  host, or run inside the backend container with
  `docker compose exec backend pytest`.
- `--reuse-db` is set in `pytest.ini`; pytest-django creates
  `tradevision_test` on first run and reuses it.
- `config.settings.testing` forces Celery tasks to run eagerly, so no
  broker workers are needed to run the suite.
- A known set of pre-existing test failures exists (journal, dashboard,
  recommendations, accounts, audit_log, market_data, replay,
  rule_engine, trader_memory); they are unrelated to local setup.

## 7. Optional: Zerodha integration

The platform is broker-agnostic and ships with a **mock** market-data
provider by default (`MARKET_DATA_PROVIDER=mock`). The system boots and
runs fully without any Zerodha credentials — `ZERODHA_API_KEY` and
`ZERODHA_ACCESS_TOKEN` default to empty strings in
`config/settings/base.py`.

Zerodha is an **optional, separate** configuration step:

1. Set `MARKET_DATA_PROVIDER=zerodha` in `infra/.env`.
2. Obtain a Kite Connect access token out-of-band (this repo does **not**
   implement the `request_token` → `generate_session` login flow).
3. Set `ZERODHA_API_KEY` and `ZERODHA_ACCESS_TOKEN` in `infra/.env`.

The access token is short-lived (expires daily). Skip this section
entirely unless you are actively working on live-market integration.

---

## Findings

Issues discovered while verifying local development:

1. **PgBouncer image unavailable — FIXED.** `bitnami/pgbouncer:1.23.1`
   no longer resolves on Docker Hub; the service now uses
   `edoburu/pgbouncer` (see the note in [section 2](#2-bring-up-the-stack)).
2. **`seed_admin` management command raised `TypeError` — FIXED.**
   `create_superuser` was called without `username`. The command now
   derives a unique `username` from the email local-part. Log in at
   `http://localhost:5173/login` with `admin` / `changeme123`.
3. **`makemigrations --check` reports drift** — **FIXED.** The `dashboard`
   app's migrations lived in nested packages
   (`apps/dashboard/infrastructure/{trading_core,analytics_risk}/migrations/`)
   that Django never loads, so every `dashboard` read-model table was missing
   (e.g. `GET /api/v1/dashboard/home/summary/` 500'd on
   `relation "dashboard_homesummary" does not exist`). The nested packages were
   removed and `apps/dashboard/migrations/0001_initial.py` generated from the
   current models; `makemigrations --check` is now clean for the whole project.
   The orphaned TimescaleDB hypertable migration was dropped (UUID primary keys
   exclude the partitioning column, which TimescaleDB rejects, and nothing uses
   TimescaleDB features).
4. **List endpoints returned bare arrays — FIXED.** `RiskDecisionListView`,
   `RecommendationListView`, and `MemoryEntryListView` overrode `get()` and
   bypassed DRF's global `PageNumberPagination`, so the `/risk`,
   `/recommendations`, and `/memory` pages crashed (`data.results.length` was
   undefined). The three views now return `{count, next, previous, results}`
   envelopes like the dashboard/signals/patterns/news endpoints.
4. **Vite did not proxy `/api` to Django — FIXED.** The frontend
   container had stale generated `vite.config.js`/`vite.config.d.ts`
   artifacts shadowing `vite.config.ts`; those are removed and the TS
   config now proxies `/api` and `/ws` to `backend:8000`, so the relative
   `API_BASE_URL` works directly on `http://localhost:5173`. A dev-only
   `__debug__/` URL pattern was also added to the root URLconf so the
   Django Debug Toolbar's `djdt` namespace resolves (previously every
   successful request 500'd with `NoReverseMatch`).
