# Frontend production audit

> Workstream WS6 — production-readiness audit of the Vite + React + TypeScript
> SPA plus one small fix aligned with backend rate limiting (WS2).

## Stack

Vite 5 + React 18 + TypeScript 5 + Tailwind, react-router-dom, recharts,
lucide-react. No state library (Context-based). No test framework, no ESLint —
`lint` is `tsc --noEmit`, `build` is `tsc -b && vite build`.

## CI-ready facts

- `package-lock.json` is present, canonical, and valid; `npm ci` works.
- `npm run lint` (tsc --noEmit) is clean on the current tree.
- `npm audit --audit-level=high --omit=dev` is a valid CI gate (used in WS1 CI).
- Build (`tsc -b && vite build`) succeeds (~4 min on this machine).
- No UI test framework exists — the only automated coverage is the TypeScript
  compiler plus a smoke script (`npm run smoke`, tsx). See gaps below.

## Change made

`src/types/common.ts` — added `TooManyRequests: 429` to `HttpStatus`. The
backend now returns 429 from DRF throttling (WS2: `anon=120/hour`,
`user=6000/hour`, `auth=15/min`, `api_keys=30/hour`), so the enumerated
special-status codes are accurate. DRF throttle responses use the `{detail}`
shape, which `apiFetch`/`normalizeError` already surface as
`message = "Request was throttled."` with `status=429`, so no retry logic was
added (retrying a throttled request immediately is counterproductive).

## Findings

### Clean

- `src/api/client.ts` is production-sound: Bearer JWT on every request;
  single-flight 401→refresh→retry; network errors normalized; both error
  shapes (`{error:{code,message}}` envelope and DRF field errors) handled;
  decimals stay strings; no CSRF dependency; manual retry only for POSTs
  (never auto-retry expensive research jobs).
- Token storage (`src/auth/tokens.ts`): access token in memory only, refresh
  token in localStorage, per `09_SECURITY_AND_GUIDE.md`. No cookies used, so
  CORS credentials stay disabled (matches backend).
- API-key auth is isolated to a header utility; the SPA itself uses JWT only.
- The SPA uses REST only — no WebSocket client is wired up. The dashboard
  WebSocket endpoints hardened in WS3 are not consumed by this frontend yet;
  that is a future work item, not a defect.
- `accountId` is taken from the URL route param and passed to the analytics
  APIs; combined with the WS5 ownership check the server rejects any
  cross-account read.

### Issues (documented, actioned or deferred)

1. **Stale `frontend/.env`** — untracked and gitignored, contains
   `DATABASE_URL=file:/home/z/my-project/db/custom.db`, which is stale
   (references a different machine) and irrelevant to this SPA (the backend's
   DB URL belongs in backend settings, not `VITE_*`). It is inert — no
   `VITE_*` vars are set, so the client falls back to `/api/v1`. **Action:**
   leave it; it is gitignored and cannot leak into CI or builds. Recommended
   cleanup: delete the file locally and use `VITE_API_BASE_URL` when needed.
2. **No automated UI tests** — no Vitest/Jest/Playwright/Cypress. The SPA is
   validated only by `tsc --noEmit` and the build. **Deferred:** adding a test
   framework is a larger change; flagged for the report.
3. **`HttpStatus` was dead code** — previously unused; the 429 entry keeps it
   accurate for future special-casing (e.g., a "slow down" banner).

## Verification

```bash
cd frontend
npm run lint   # tsc --noEmit — clean
npm run build  # tsc -b && vite build — succeeds
```

Node toolchain note: this machine has no system node; CI uses the
`setup-node` action (WS1).