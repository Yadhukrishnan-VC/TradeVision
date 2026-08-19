# CI — Continuous Integration

> Workstream WS1 — production hardening. Pipeline definition:
> `.github/workflows/ci.yml`.

## Purpose

Give every push / PR a fast, deterministic, machine-readable signal that the
backend and frontend still build, pass their tests, and carry no obvious
bug-risk regressions. It is the outer safety net for the parallel production
hardening workstreams (WS1–WS7).

## Pipeline overview

Runs on every push to `trading-core` / `main` and every pull request.
Concurrency is cancelled in favour of the newest commit on the same ref.

| Job | What it gates | Fails when |
| --- | --- | --- |
| `backend` | ruff bug-risk lint · `manage.py check` · migration-drift guard · full `pytest` | A test fails, Django config is invalid, or bug-risk lint regresses |
| `frontend` | `tsc --noEmit` typecheck · `vite build` · `npm audit` (prod deps) | Type errors, build failure, or a high/critical prod-dependency advisory |
| `security` | `pip-audit` on `requirements/base.txt` | A published CVE in a runtime Python dependency |

## Backend job

- Services: PostgreSQL 16 (`tradevision_db` / `tradevision`) and Redis 7, both
  health-gated so tests never race a cold container.
- Env wired exactly as local test runs:
  `POSTGRES_*`, `REDIS_URL=redis://127.0.0.1:6379/0`,
  `EVENT_BUS_IMPLEMENTATION=fake`, `DJANGO_SECRET_KEY` (test-only value).
- Install: `pip install -r requirements/dev.txt` (includes pytest, ruff, mypy).

### Lint

The repository is **not** clean under ruff's full default rule set
(~1800 findings on a fresh checkout) and ruff `format --check` reports ~440
files would be reformatted. Running the full rule set in CI would produce a
permanently red pipeline and zero signal. The CI gate therefore runs the
**bug-risk subset**:

```bash
ruff check --select E9,F63,F7,F82 --extend-exclude apps/execution .
```

`E9`/`F63`/`F7`/`F82` are unambiguous code-construction bugs (syntax errors,
undefined names, unused imports). `apps/execution` is excluded because it
carries one pre-existing `F821 Undefined name datetime` (line 188 of
`apps/execution/infrastructure/repositories.py`); it is tracked as a known
finding — see SECURITY_HARDENING.md and the final implementation report. When
that bug is fixed, drop the exclude.

The full lint debt (rule selection, format drift) is out of scope for WS1 and
documented here rather than silently fixed — see **Known CI debt**.

### Migration drift guard

```bash
python manage.py makemigrations --check --dry-run --settings config.settings.testing
```

`--check` exits non-zero when models differ from migrations. It currently
reports drift in:

- `rule_engine`, `signals_engine`, `trader_memory` — owned by **Batch 1**
  (migration drift workstream, in flight in parallel).
- `recommendations` — **unassigned**; flagged in the final report.

The step runs with `continue-on-error: true` so it never red-lights the
pipeline, but its output is visible on every run: it doubles as a live tracker
that flips green exactly when Batch 1 + the recommendations drift land.
**Action:** flip this step to blocking (remove `continue-on-error`) once those
migrations are merged.

### Tests

```bash
pytest
```

`pytest.ini` already selects `config.settings.testing` (eager Celery, in-memory
channel layer, dummy cache) and `--reuse-db`. Redis is still required for the
session-scoped `redis_client` fixture used by market-data / event-bus tests —
hence the Redis service.

## Frontend job

- Node 22 (Vite 5 / TS 5 family), `npm ci` against the committed
  `package-lock.json` (canonical lockfile; `bun.lock` is present but not used
  in CI).
- `npm run lint` — the repo's lint script is `tsc --noEmit` (typecheck only;
  there is no ESLint/Prettier). This is intentional and documented in
  FRONTEND_PRODUCTION_AUDIT.md.
- `npm run build` — `tsc -b && vite build`; proves the production bundle.
- `npm audit --audit-level=high --omit=dev` — blocks on high/critical
  advisories in runtime dependencies only.

## Security job

- `pypa/gh-action-pip-audit` scans `requirements/base.txt` (runtime deps only)
  against the OSV database. Dev-only deps are intentionally not scanned here
  because they cannot reach production.

## Running locally

```bash
# Backend: identical to CI (needs local postgres + redis running)
cd backend
export POSTGRES_DB=tradevision_db POSTGRES_USER=tradevision POSTGRES_PASSWORD=tradevision_password \
       POSTGRES_HOST=localhost POSTGRES_PORT=5432 REDIS_URL=redis://localhost:6379/0 \
       EVENT_BUS_IMPLEMENTATION=fake
.venv/bin/python -m ruff check --select E9,F63,F7,F82 --extend-exclude apps/execution .
.venv/bin/python manage.py check --settings config.settings.testing
.venv/bin/python manage.py makemigrations --check --dry-run --settings config.settings.testing
.venv/bin/pytest

# Frontend (bootstrap node if the host has none, e.g.):
#   export PATH=/tmp/opencode/node-v24.11.1-linux-x64/bin:$PATH
cd frontend
npm ci && npm run lint && npm run build
```

## Known CI debt (deliberately not fixed in WS1)

| Item | Status | Owner |
| --- | --- | --- |
| Full ruff rule set (E4/E7/F, ~1800 findings) | Not enabled — gate uses bug-risk subset | Follow-up hardening batch |
| `ruff format` drift (~440 files) | Not enforced | Follow-up batch |
| `mypy` / django-stubs | Installed, not wired into CI | Follow-up batch |
| `makemigrations --check` blocking | Currently non-blocking due to Batch 1 + recommendations drift | Batch 1; then flip |
| Frontend unit tests (vitest/jest) | None exist; nothing to run | See FRONTEND_PRODUCTION_AUDIT.md |

These were left as-is to respect the "no architectural rewrite / smallest
production-safe change" rule: enabling them now would make CI fail for
pre-existing reasons unrelated to the code under change.
