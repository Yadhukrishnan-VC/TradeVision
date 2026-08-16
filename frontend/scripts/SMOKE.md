# Smoke Validation

Per the build order: **Phase 0 → Phase 1 → Smoke validation → Phase 2 Research**.

This directory contains a TypeScript smoke-test script that exercises the verified
API contracts against a live backend before the research UI is built around them.

## Status

**Skipped.** No live backend URL was provided at build time. The frontend
proceeds against the documented schemas defensively (per decision #4). When a
live environment becomes reachable, re-run this script to validate the ⚠
endpoint bodies.

## How to run

```bash
# 1. Set the backend URL + smoke credentials
export VITE_API_BASE_URL=http://your-backend.example.com/api/v1
export SMOKE_USERNAME=admin
export SMOKE_PASSWORD=secret

# 2. Run from the project root
npm run smoke
```

The script will:

1. `POST /auth/login/` — verify JWT issuance
2. `POST /auth/refresh/` — verify rotation
3. `GET /auth/me/` — verify normal protected endpoint
4. `GET /dashboard/home/summary/` — verify trading-core Bearer-JWT access
5. `GET /auth/api-keys/` — defensive (records failure as a note, not error)
6. `POST /backtesting/runs/` — verify backtest creation
7. `GET /backtesting/runs/:id/` — verify run detail fetch
8. `POST /backtesting/cost-sensitivity/` — verify a synchronous research POST

## Exit codes

- `0` — all checks passed (or all critical failures were auth-related and
  decision #1's caveat applied)
- `1` — at least one check failed. Failures do **not** block the build; they
  are reported so the user can decide whether the contract drifted.

## What this catches

- Stale `.md` payload shapes (the ⚠ endpoints)
- Auth wiring regressions (per decision #1, 403 = authorization failure)
- Backtest POST/GET field drift
- Sync research endpoint behavior (timeout vs success)
