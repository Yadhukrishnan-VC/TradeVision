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

> **Known blocker — PgBouncer image is unavailable.**
> The `pgbouncer` service pins `bitnami/pgbouncer:1.23.1`. Bitnami
> migrated these images off Docker Hub and the tag no longer resolves
> (`pull` returns "not found", as does every other `bitnami/pgbouncer`
> tag including `latest`). The full stack therefore does **not** come up
> cleanly in its current form. This is a pre-existing infrastructure bug
> and is out of scope for this onboarding documentation to fix. See
> [Findings](#findings). The data tier (Postgres + Redis) and the host
> test suite are unaffected.

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

> **Known bug — `seed_admin` currently fails.**
> The command calls `User.objects.create_superuser(email=..., password=...)`
> without a `username`, but the custom `accounts.User` uses Django's
> default `UserManager` (per migration `0004`), whose `create_superuser`
> requires `username`. Running it raises
> `TypeError: UserManager.create_superuser() missing 1 required
> positional argument: 'username'` (verified empirically). It is a
> pre-existing bug and out of scope for this documentation to fix.

A working alternative while the bug exists:

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

Pre-existing issues discovered while verifying local development (not
fixed — out of scope for documentation):

1. **PgBouncer image unavailable (blocks full stack).**
   `infra/docker-compose.yml` pins `bitnami/pgbouncer:1.23.1`, which no
   longer resolves on Docker Hub (the whole `bitnami/pgbouncer`
   repository is gone). `docker compose up` fails at the `pgbouncer`
   service. Postgres, Redis, the backend image build, and the host test
   suite are unaffected.
2. **`seed_admin` management command raises `TypeError`.**
   `create_superuser` is called without `username`; the custom
   `accounts.User` uses Django's default `UserManager` which requires it.
3. **`makemigrations --check` reports drift** in pre-existing apps
   (`rule_engine`, `signals_engine`, `trader_memory`). Unrelated to local
   setup and pre-existing.
