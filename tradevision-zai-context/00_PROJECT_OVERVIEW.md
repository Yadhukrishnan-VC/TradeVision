# TradeVision AI — Frontend Context Package for Z.ai

Purpose: give Z.ai everything it needs to build the TradeVision AI Dashboard frontend from the real repository, with no fabrication and no backend changes.

## Context Status

TradeVision frontend context status:

**READY FOR Z.AI**

Authentication P0:
**RESOLVED**

| Item | Status |
|---|---|
| JWT authentication | **VERIFIED** |
| API-key scope authentication | **VERIFIED** |
| CORS | **VERIFIED** |
| Claude authentication audit | **PASSED** |

Remaining backend gaps:
See `08_GAPS_BLACKLIST_AND_ASSUMPTIONS.md`.

Important:
The frontend must not invent APIs for documented backend gaps.

## What TradeVision Is

TradeVision AI is a rule-based algorithmic trading / research platform (India / NSE-centric, Zerodha-style concepts). It:

- Ingests live market data and technical-analysis webhooks (TradingView, Chartink).
- Runs a rule engine (`rule_engine`) that fires 8 built-in trading rules on incoming signals; each firing emits a domain event that may produce orders.
- Executes orders through a safe paper-execution engine (fill mode FULL_FILL, simulated time).
- Replays historical candles to backtest rules, then derives quantitative edge metrics (expectancy, profit factor, Sharpe, Sortino, max drawdown, benchmark return, IS/OOS splits, per-regime and per-rule attribution).
- Validates rules empirically: walk-forward OOS distribution, cost-sensitivity (breakeven commission/slippage), edge validation, and a rule-firing validation gate (ADR-029 go/no-go per rule+regime).
- Surfaces operator dashboards: trading-core (positions/orders/trades), analytics & risk (PnL, daily rollup, performance, risk summary), portfolio, journal, audit log, pipeline health, portfolio reconciliation.
- Tracks state in a Postgres DB and uses Celery/Redis for background backtest runs and the event bus.

## Tech Stack (verified)

| Layer | Technology | SOURCE |
|---|---|---|
| Backend | Python 3.12.3 | repo runtime |
| Web framework | Django 6.0.7 | `backend/requirements/base.txt` |
| API framework | Django REST Framework 3.15.2 | `backend/requirements/base.txt` |
| Auth tokens | djangorestframework-simplejwt (>=5.3,<6) | `backend/requirements/base.txt` |
| DB / queue | PostgreSQL + Redis (Celery broker) | `backend/config/settings/base.py` |
| Frontend (scaffold) | React 18.3.1 + Vite 5.3.1 + TypeScript 5.2.2 + Tailwind CSS + lucide-react | `frontend/package.json` |

## Repository Layout

```
backend/
  config/            Django project: settings/{base,dev,development,prod,staging,test,testing}.py, urls.py, celery.py, wsgi.py
  apps/              ~36 Django apps (see 01_SYSTEM_ARCHITECTURE.md)
    accounts/        users, accounts, API keys, JWT issuance
    market_data/     Instrument, Candle models
    technical_analysis/ TASnapshot model + TA webhook ingestion
    rule_engine/     rules + RuleConfig/RuleExecution + firing gate
    execution/       paper execution engine, orders/fills
    portfolio/       capital, positions
    risk_management/ risk decisions, kill switch
    backtesting/     replay engine, run_stats, walk-forward, edge validation, cost sensitivity
    dashboard/       trading_core + analytics_risk read APIs
    journal, audit_log, watchlist, signals_engine, pattern_engine,
    recommendations, trader_memory, ingestion, pipeline_health,
    portfolio_reconciliation, common, eventbus, health
frontend/
  package.json, vite.config.ts, tailwind.config.ts, tsconfig.json, index.html
  src/App.tsx        placeholder: "TradeVision AI Dashboard / Phase 8 — Frontend Interface Foundation"
  src/main.tsx       React entry
  src/               (no pages, no routes, no API client yet)
```

## Git State (as of this package)

- Branch: `front_end`
- HEAD: `698c35a` — "feat: ADR-029 — rule firing validation gate (go/no-go per rule+regime)"
- Working tree: clean except 2 untracked patch files at repo root (`context-honesty-1.patch`, `rule-validation-gate-1.patch`). Do not modify these.
- Repo size: ~599 MB.

## Frontend Deliverable Scope

Z.ai must build a **React + Vite + Tailwind** SPA implementing the pages listed in `05_DATA_PAGES_AND_IA.md` against the real backend API described in `04_API_CONTRACT.md`. Read the following files in order:

1. `01_SYSTEM_ARCHITECTURE.md` — backend mental model
2. `02_FRONTEND_AND_DESIGN.md` — frontend foundation + design system
3. `03_AUTHENTICATION.md` — how login/refresh/JWT/API-key auth work
4. `04_API_CONTRACT.md` — every verified endpoint + response shape
5. `05_DATA_PAGES_AND_IA.md` — data models, page map, and navigation IA
6. `06_CHARTS.md` — chart inventory and charting rules
7. `07_DATA_STATES_AND_RESEARCH.md` — error envelope, data states, research features
8. `08_GAPS_BLACKLIST_AND_ASSUMPTIONS.md` — backend gaps + endpoint blacklist + assumptions
9. `09_SECURITY_AND_GUIDE.md` — security/compliance + Z.ai implementation rules

## Conventions Used In This Package

- Every important fact carries `SOURCE: <path>`.
- `VERIFIED` = read directly from source code.
- `NOT VERIFIED` = not confirmed in source; do not treat as truth.
- `RESPONSE STRUCTURE REQUIRES VERIFICATION` = the endpoint exists, but its exact JSON body was not fully traced; treat the documented shape as provisional.
- `BACKEND GAP` = a feature the UI would need that does not exist in the backend.
- Never invent metrics, fields, endpoints, or strategies. Where data is unavailable, the UI must render `null`/empty/`--` — never fabricate zero.