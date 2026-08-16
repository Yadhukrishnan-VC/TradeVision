# TradeVision Frontend — Worklog

---
Task ID: 1
Agent: Main (Super Z)
Task: Build the TradeVision AI React+Vite SPA frontend against the documented backend contracts in /home/z/my-project/upload/*.md, per user decisions #1–#12.

Work Log:
- Read all 10 markdown context files (00–09).
- Produced a frontend implementation plan + page-to-API mapping.
- Surfaced 12 contradictions / open questions; received decisions from user.
- Re-ordered build per user correction: Phase 0 → Phase 1 → Smoke validation → Phase 2 Research → Phases 3–6.
- Followed authoritative hierarchy: latest verified P0 status overrides stale auth-gap statement in older markdown.

Phase 0 — Foundation:
- Scaffolded Vite + React 18 + TypeScript 5 + Tailwind 3 + lucide-react at /home/z/my-project/.
- Configured @/ path alias in both tsconfig.json and vite.config.ts.
- API client: Bearer JWT injection, error-envelope + DRF field-error parsing, paginated/bare response handling, 401→silent-refresh→single-retry→/login.
- Auth context: access token in memory, refresh token in localStorage, boot-time hydration via /auth/refresh/, /auth/me/ fetch on success.
- Route guard (RequireAuth) + AppShell (Sidebar + TopBar).
- Design-system primitives: Card, StatCard, Chip (regime/ADR-029 gate/run-status/classification/has-edge tone helpers), Button, Spinner, Skeleton, EmptyState, Alert, Tabs, Breadcrumbs, DataTable (sortable, numeric right-aligned, hover, loading skeleton, empty state).
- Hooks: useFetch (data-state machine idle/loading/success/empty/error), usePoll (for backtest runs + export status).
- lib/format: fmtInr, fmtPct, fmtRatio, fmtDecimal, fmtInt, toNum (null-safe), isMissing, pnlColor.
- TypeScript types mirroring every documented contract: common (envelope, pagination), auth, dashboard, research (VERIFIED full shapes), rules, secondary (defensive interfaces for ⚠ endpoints).
- API modules: client, auth, dashboard, analytics, research, rules, system, secondary.
- Smoke script at scripts/smoke.ts — exercises 8 request classes (login, refresh, /auth/me/, trading-core, scope-gated, backtest POST/GET, sync research). Skipped without a backend URL per decision #4; documented in scripts/SMOKE.md.

Phase 1 — Login:
- POST /auth/login/ against verified contract.
- Handles invalid_credentials / account_disabled error codes.
- Never logs tokens/password.

Phase 2 — Research (the differentiator):
- BacktestList: create form (POST /backtesting/runs/) + localStorage-backed recently-viewed panel. Explicit "no list endpoint documented" notice per decision #5.
- BacktestDetail: polls GET /backtesting/runs/:id/ until COMPLETED/FAILED, then renders full run_stats dashboard — equity curve (cumulative from trades[].net_pnl), IS/OOS equity curves, by_regime bars, by_rule horizontal bars, trades DataTable, max_drawdown_pct as StatCard (NOT a chart — gap P4), 4-tab layout (Overview, By Regime, By Rule, IS/OOS).
- WalkForward: VERIFIED request + response. Per-window OOS expectancy bar chart, distribution stat cards (min/max/median/count_positive), per-window detail table. 120s timeout, manual retry.
- EdgeValidation: VERIFIED request + response. Rule × cost-level matrix (baseline_has_edge vs realistic_cost_has_edge + flipped), edge_criterion panel rendered as returned, per-rule drill-down with has_edge True/False/null chips.
- CostSensitivity: VERIFIED request + response. Classification badges (BREAKEVEN_FOUND / NEVER_PROFITABLE / SURVIVES_FULL_RANGE), per-rule expectancy-vs-cost line chart with breakeven markers.
- All sync research POSTs use useSyncResearch hook with 120s client timeout, "still processing" UI, manual retry only, no fake client-side cancellation (decision #10).
- Chart components wrapped in isolated modules (EquityCurve, BarChart, LineChart, Donut, Histogram) so the chart library is swappable (decision #8).

Phase 3 — Dashboard (trading_core):
- DashboardHome (GET /dashboard/home/summary/) — StatCards for all 8 verified fields + quick links.
- Portfolio (GET /dashboard/portfolio/composition/) — totals cards + holdings donut (allocation_pct) + table.
- HoldingDetail (GET /dashboard/portfolio/holdings/:symbol/).
- Positions + PositionDetail.
- Orders + OrderDetail.
- Trades + TradesOpen + TradesClosed.
- TradeExportStatus (GET /dashboard/trades/history/export/:id/) — polls status; renders download link only if response supplies one. ⚠ per decision #6.

Phase 4 — Analytics & Risk (defensive):
- AnalyticsPnl / PnlDaily / Performance / Risk — all per-account, route-param-driven. Per-account sub-nav between PnL/Daily/Performance/Risk. Defensive interfaces render documented fields; unknown keys shown as JSON for transparency. ⚠ warning banner on each.

Phase 5 — Rules, Journal, Audit, System:
- Rules: GET /rule-engine/configs/ — ADR-029 GO/NO_GO/INSUFFICIENT_DATA chips per rule+regime.
- RuleDetail + RuleExecutions.
- Journal + JournalDetail (read-only).
- Audit (read-only, authoritative).
- PipelineHealth + Health component checks (db/cache/celery/eventbus/system — unauthenticated).
- Recommendations: list + accept/reject with confirmation modal.
- Signals.
- Patterns (runs + historical-vectors tabs).
- Watchlist: GET/DELETE only per decision #7. PATCH deferred — code throws if invoked.
- PortfolioSummary.
- RiskDecisions.
- KillSwitch: role-gated (owner/staff only) + confirmation modal per 09.
- Reconciliation (drift summary + list).
- TraderMemory (entries + strategy projections).
- RawIngestionEvents (secondary, read-only per decision #12).

Phase 6 — Polish:
- Every fetch path handles loading/success/error/empty per the data-state machine in 07.
- INR (₹1,234.56), %, ratio (2dp), integer formatting everywhere.
- Tabular numbers (font-mono tabular-nums) on numeric columns.
- RTL-safe spacing (gap/py/px).
- AA contrast (slate-900 on white; indigo-600 actions; emerald/rose/amber for status).
- 404 catch-all redirects to /.
- Production build green (no TS errors). Bundles: main 65KB gzipped, recharts lazy-loaded only on chart pages.

Smoke validation script ready at scripts/smoke.ts. Currently skipped (no live backend URL provided). Re-run with VITE_API_BASE_URL + SMOKE_USERNAME/PASSWORD env vars to validate the ⚠ endpoint bodies.

Stage Summary:
- Frontend complete: 36 page modules, 11 API modules, full design-system, types matching documented contracts.
- No fabricated endpoints, metrics, or strategies.
- Backend gaps (P1 OHLC, P2 export, P3 top-level equity_curve, P4 drawdown series, P7 dead auth, P8 unmounted apps) honored.
- All documented blacklists respected (no calls to /accounts/*, /metrics/, /admin/, webhooks, /portfolio/fills/ write).
- ADR-029 gate semantics correctly rendered (GO/NO_GO/INSUFFICIENT_DATA; null has_edge distinct from False).
- Build verified end-to-end in browser: Login renders, route guards redirect, no page errors, no console errors.
- To run: `npm install && npm run dev` from /home/z/my-project/.
- To validate against a backend: `VITE_API_BASE_URL=... SMOKE_USERNAME=... SMOKE_PASSWORD=... npm run smoke`.
