# 02 — Frontend Stack, Foundation, and Design System

## What Already Exists (VERIFIED)

The `frontend/` directory is a minimal Vite scaffold — a placeholder only. There are **no pages, no routes, no state management, no API client, no components**.

- `frontend/package.json`:
  - name `tradevision-frontend`, version `1.0.0`
  - dependencies: `react ^18.3.1`, `react-dom ^18.3.1`, `lucide-react ^0.400.0`
  - devDependencies: `vite ^5.3.1`, `typescript ^5.2.2`, `@vitejs/plugin-react ^4.3.1`, `@types/react`, `@types/react-dom`
- `frontend/src/main.tsx` — React entry.
- `frontend/src/App.tsx` — renders "TradeVision AI Dashboard" and "Phase 8 — Frontend Interface Foundation" placeholder.
- `frontend/tailwind.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/vite.config.ts` — standard Vite/Tailwind config.
- `tailwind.config.ts` content is empty of custom theme extensions (default Tailwind palette only).

## What Z.ai Must Add

The scaffold is the starting point. Build the SPA on React 18 + TypeScript + Tailwind + lucide-react. Recommended structure (follow existing conventions; Vite + TS + Tailwind are fixed):

```
frontend/src/
  api/            fetch client + typed endpoint modules (contracts in 04)
  auth/           token storage, login/refresh logic, route guards
  components/     shared UI components (charts, cards, tables, spinners)
  pages/          one file per page in 05_DATA_PAGES_AND_IA.md
  routes.tsx      route table (see 05_DATA_PAGES_AND_IA.md)
  lib/            formatting (INR, %, decimals), date utils
  types/          TypeScript interfaces mirroring 04/05 contracts
```

## Non-negotiable

- Do NOT change the backend to "fix" missing data. Use `BACKEND GAP` markers and render empty/`--` states.
- Do NOT rename the existing scaffold or remove its tooling (Vite/TS/Tailwind are the fixed stack).
- All numeric values arriving from the API are **strings** (see 04 — Decimals are serialized with `str()`). Convert at render time; never assume `number`.
- Never hardcode trade/performance figures. Everything renders from API data only.

## Design System

Base: Tailwind CSS (default palette — `frontend/tailwind.config.ts` has no custom theme extensions). Icons: lucide-react (installed). This section defines the design language Z.ai should implement in Tailwind utilities — it is a *spec*, not backend data.

### Palette (Tailwind default tokens)

- Background: `slate-50` / `white`; surface cards: `white` with `border-slate-200`, `shadow-sm`.
- Text: `slate-900` primary, `slate-500` secondary, `slate-400` muted.
- Accent: `indigo-600` (primary actions), `blue-500` (links).
- Semantic: profit `emerald-600`, loss `rose-600`; neutral `slate-500`.
- Status (ADR-029 gate): GO `emerald-600`, NO_GO `rose-600`, INSUFFICIENT_DATA `amber-500`.
- Regime chips: pastel set (`emerald-50/100`, `sky-50/100`, `violet-50/100`, `amber-50/100`, ...) — regimes are arbitrary strings, so chips must tolerate unknown values (fallback `slate-50`).

### Typography

- Use system font stack; numeric/metrics in `font-mono` (tabular numbers) — money and ratios are strings, so mono alignment helps scanning.
- Headings `text-lg/xl font-semibold tracking-tight`; page titles `text-2xl font-bold`.

### Components (build these)

1. **StatCard** — label + value + optional delta (up/down coloring by sign, not by direction).
2. **Card** — white surface, border, padding, optional header + action slot.
3. **DataTable** — sortable headers, right-aligned numeric columns, row hover, empty state slot, loading skeleton rows.
4. **Chip/Badge** — for regime, rule_id, status (PENDING/RUNNING/COMPLETED/FAILED, GO/NO_GO/INSUFFICIENT_DATA, BREAKEVEN_FOUND/NEVER_PROFITABLE/SURVIVES_FULL_RANGE, order status).
5. **Tabs** — for Research sub-nav and detail-page sections.
6. **Buttons** — primary/secondary/ghost/danger; loading spinner inside primary on POSTs.
7. **Spinner & Skeleton** — `animate-pulse` rows/cards.
8. **EmptyState** — icon + message + optional CTA (used for every `null`/empty data case).
9. **Toast/Alert** — inline error banner using the `error.code` from the API envelope.
10. **EquityCurve / BarChart / LineChart / Donut** — from the chart inventory in 06_CHARTS.md.

### Layout

- App shell: fixed left sidebar (collapsible, `w-64`/`w-16`), top bar `h-14`, content max-width `max-w-7xl mx-auto p-6`.
- Detail pages: two-column on `lg` (main content + sidebar stats), stacked on mobile.

### Accessibility & polish

- Contrast AA on text; focus-visible rings (`ring-indigo-500`).
- All number cells `text-right font-mono tabular-nums`.
- Loading = skeletons; empty = EmptyState; error = inline Alert (never a blank page).
- Keep RTL-safe spacing (use gap/py/px, not `ml-`/`mr-` alone where direction matters).