# 09 — Security, Compliance, and Frontend Guide for Z.ai

## Security and Compliance

### Secrets (non-negotiable)

- **The frontend never receives or displays secrets.** No passwords (beyond the login form), no JWT signing keys, no broker API credentials, no webhook tokens.
- Webhook URLs (`/api/v1/ingestion/webhooks/tradingview/<token>/`, `.../chartink/<token>/`, `/api/v1/technical-analysis/webhooks/tradingview/<token>/`) contain per-provider tokens. The dashboard does NOT render or link these paths — they are provider-facing. Do not build a page that shows webhook URLs/tokens.
- This package contains NO secrets. (Final validation re-checks.)

### Token handling (JWT)

- Access token ~15 min, refresh ~7 days, rotation on refresh. Store access in memory (React context) and refresh token in `localStorage` (or `httpOnly` cookie if backend supports it — it does not currently; keep the simple frontend storage).
- On 401 from any request: attempt one silent refresh, then re-dispatch the original request; on refresh failure → redirect to `/login`.
- Never log tokens.

### Authorization model (VERIFIED)

- `DEFAULT_PERMISSION_CLASSES = IsAuthenticated`. Role field: `owner` / `staff` / `viewer`. Some endpoints are owner/staff-only (e.g. portfolio reconciliation, kill switch). UI should hide owner/staff-only actions unless the user's role allows them (role comes from `/auth/me/`).

### Dangerous operations (guard in UI)

- `POST /portfolio/fills/` (record a fill), kill-switch activate/deactivate, recommendation accept/reject — require explicit confirmation (modal) and show the API error if rejected. Never auto-submit.
- Research POSTs create accounts + runs and are expensive — one submit button, disabled while pending.

### Compliance

- Journal and Audit Log pages must read-only display backend records (`/journal/entries/`, `/audit/entries/`) — the audit trail is authoritative; never write/modify from the UI.
- No client-side trust: all numbers come from the API; format only, never compute authoritative totals the user might act on.

### OWASP basics for the SPA

- Escape all rendered strings (React does by default — never use `dangerouslySetInnerHTML`).
- Validate all form inputs client-side for UX only; server is the source of truth (it returns 400 with the error envelope).
- Keep dependency surface small; lock versions.
- CSRF: the API uses JWT/API-key headers, not session cookies — no CSRF cookie handling needed for the SPA (do not send Django CSRF token).

## Frontend Guide for Z.ai (Implementation Rules)

These rules are non-negotiable. Violations defeat the purpose of this package.

### Golden rules

1. **Backend is the source of truth.** Every number, field, and metric the UI shows MUST come from the API contracts in `04_API_CONTRACT.md` / models in `05`. NEVER invent data, metrics, endpoints, rules, or strategies.
2. **Do NOT modify the backend.** Not for convenience, not to "fix" anything. The deliverable is frontend-only. Missing backend data = `BACKEND GAP` (08) → render empty/`--` states.
3. **Do NOT fabricate zeros.** A `null` ratio renders as `--`. A missing chart series is an EmptyState. Never convert missing → 0.
4. **Decimals are strings.** All money/ratios from the API are strings. Convert at render time. Never treat them as `number` directly (the payloads contain `"1000000"` etc.).
5. **No secrets in the frontend or in any file Z.ai writes.** No keys, tokens, passwords, webhook URLs.
6. **Errors follow the envelope.** Handle `{"error": {code, message}}` AND DRF field-error shapes (07). Show the message; never swallow errors into blank pages.
7. **No demo/static data anywhere.** Every screen renders real API data or an explicit empty/loading/error state.

### Build order

1. **Foundation**: API client (fetch wrapper with JSON envelope parsing, 401→refresh→retry), auth store (login/refresh), routing shell with sidebar/topbar, design system primitives (02).
2. **Login** page (03) — fully functional against the real contract.
3. **Research suite** — Backtests (create + poll + detail), Walk-Forward, Edge Validation, Cost Sensitivity (04/07). This is the differentiator; build it first after auth.
4. **Dashboard suite** — home summary, portfolio composition/holdings, live positions, orders, trade history (04).
5. **Analytics & Risk** — per-account PnL/daily/performance/risk (⚠ shapes — render defensively).
6. **Rules, Journal, Audit, Watchlist, Signals, Recommendations, Memory, Patterns, System pages** (05).
7. **Polish**: empty/loading/error states everywhere, INR/% formatting, tabular numbers.

### Quality bar

- TypeScript strict; every API payload gets an interface mirroring the contracts.
- Every component handles `loading | success | error | empty`.
- No `any` leaks from fetch responses — map to typed interfaces with defensive `?? null` defaults.
- Keep the stack: React 18 + Vite + TS + Tailwind + lucide-react (+ one chart lib if needed, 06).

### Do not build

- Anything that calls unmounted apps or legacy auth paths (01/03/08).
- Pages that show webhook tokens/URLs (09).
- Live price charts from market data (no endpoint — 08 P1).
- A fabricated drawdown/equity series (08 P3/P4).
- Client-side authoritative math on top of displayed metrics (09).

### When done

The result must run with `npm install` + `npm run dev` (or the existing scaffold's scripts) and render against a real backend instance. If a backend is not reachable, the app must show clean error/empty states — never a hardcoded dashboard.