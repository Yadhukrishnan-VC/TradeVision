# TradeVision AI — Architecture v1.0

> Status: **FROZEN — Approved Reference**
> Version: 1.0
> Incorporates: Kickoff Design + Principal Architecture Review + Market Intelligence Engine + Pattern Engine + Trader Memory
> Rule: No architecture changes unless explicitly requested and approved.

---

## Development Status

> Last updated: 2026-08-19

| Phase | Status | Tests | Notes |
|---|---|---|---|
| 0 — Foundation | **COMPLETE** | 206 passing | All 23 source files + 17 test files implemented |
| M2 — Deterministic Trading Setups | **COMPLETE** | 51 M2 tests passing | Long Momentum / Short Sell / Volatility Breakout setups (ADR-013), SessionFactsService, TA-handler enrichment, idempotent `RuleExecution` (commit `e6e749c`) |
| M3 — Deterministic Risk Management | **COMPLETE** | 32 tests passing | `apps.risk_management` (ADR-027): stub capital gateway (`portfolio_gateway_impl="stub"`), 9-check fail-closed pipeline, Postgres kill switch (GLOBAL→ACCOUNT→SYMBOL) with short-TTL cache, `RiskApproved`/`RiskRejected` events, `entry_price` added to M2 trigger_data |
| M4 — Portfolio & Capital Management | **COMPLETE** | 122 tests passing | `apps.portfolio` (ADR-028): authoritative `AccountCapitalState` ledger, ledger-style `Position` lifecycle, idempotent `PositionFillExecution`, 5 approved events (`positions.*` feed unmodified dashboard projections; `portfolio.*` new territory). Risk gateways swapped to real `RealCapitalGateway`/`RealPortfolioStateGateway` (`implementation_name="portfolio_v1"`, default `RISK_MANAGEMENT_GATEWAY_IMPL="portfolio"`) with stub as defensive fallback. Portfolio API at `/api/v1/portfolio/` (summary/positions/fills). Permission fix: `permission_classes` now uses scope-wrapper classes in portfolio + risk_management (was an instance ⇒ `TypeError`). Natural-form Decimal payloads + 8-dp quantize at persistence boundaries |
| 1 — Market Data | NOT STARTED | — | Next phase |
| 2 — Technical Analysis | **COMPLETE** | 60 non-DB passing | Webhook ingestion, validation, normalisation, TASnapshot persistence, Pine Script metadata, event publishing with real indicator/price data |
| 3 — Intelligence Engine | **COMPLETE** | 60 non-DB passing | TA completed handler builds IntelligencePacket with real values, publishes PacketBuilt (not enriched). Portfolio/risk enrichment pipeline (PortfolioRiskContextBuilder + intelligence:enriched) deferred to Phase 9. |
| 4 — Rule Engine | **COMPLETE** | 60 non-DB passing | SUBSCRIBED_EVENTS populated, enriched packet handler, rule evaluation and firing pipeline wired |
| 5 — AI + Recommendations + Trader Memory | **PARTIAL** | 53 passing (AI-5B/AI-5C/AI-5D batch targets) | DeepSeek/Gemini complete() implemented with retry, ModelRouter decision feeds provider selection, orchestrator calls real provider, fallback only on failure. AI-5B: PromptManager forwards all 8 Market Context scores/pattern note; base.j2 emits `direction` (BUY/SELL/WATCH/AVOID) matching live AIResponseSchema; Recommendation persists provider + correlation_id end-to-end (service → task → event handler). AI-5C: orchestrator provider loop records breaker record_success/record_failure on the shared `ai-provider-{name}` circuits so the router excludes OPEN providers after N failures (HALF_OPEN eligible); end-to-end reachability trace test added. AI-5D: `_evaluate_confidence` reads the latest `PatternAnalysisRun` per symbol and feeds numeric `confidence_contribution` + `historical_recommendation_accuracy` into `ConfidenceEngine.evaluate()` (additive contribution + percentage accuracy penalty mirroring the data-quality block); gated on existing `CONFIDENCE_ENGINE_V2_ENABLED` (default False) — fills ADR-023 §2.c trader-memory calibration hook, no new flag, no migration. Cleanup deferred: `tasks.py::evaluate_confidence`/`route_and_render` are orphaned Celery tasks (no dispatch site). Keys: `backend/.env` has `GEMINI_API_KEY=test-key` (placeholder — real credential still required); `DEEPSEEK_API_KEY` unset. |
| 6 — Notifications + WebSocket | NOT STARTED | — | — |
| 7 — News + Announcements + Global Markets | NOT STARTED | — | — |
| 8 — Frontend Dashboard | NOT STARTED | — | — |
| 9 — Portfolio + Options Chain | **PARTIAL** | 122 passing | Backend `apps.portfolio` complete (ADR-028): authoritative capital ledger, position lifecycle, real risk gateways (`portfolio_v1`), `/api/v1/portfolio/` API. Frontend portfolio page, options analysis, and options-aware AI context remain NOT STARTED |
| 10 — Pattern Engine | **COMPLETE** | 48 passing (DB-backed) | Deterministic historical session similarity (ADR-007 §5.2 weights), subscribes to intelligence.PacketBuilt, publishes pattern_engine.PatternAnalysisCompleted, Trader Memory accuracy enrichment flag-gated; frozen apps untouched |
| 11 — Backtesting + Calibration | **PARTIAL** | 170 passing | `apps.backtesting` single-run replay engine (`BacktestRunnerService`, `BacktestStatsService`, walk-forward service/API) + research integrity suite (`backend/tests/research_integrity`, 17 adversarial tests via the real event chain). RESEARCH-INTEGRITY-1: IS/OOS split now uses first-fill simulated `occurred_at` (was wall-clock `order.created_at` → every replay trade landed in OOS). RESEARCH-INTEGRITY-2: bar-open fill requires a real `open` (was falling back to the bar's close = look-ahead). See `docs/RESEARCH_INTEGRITY.md` |
| 12 — Hardening | NOT STARTED | — | — |
| Live/Paper Readiness (dev-ops) | **COMPLETE** | 16 tests passing | Runtime deps declared in `requirements/base.txt` (fresh venv rebuild proves `manage.py check` clean with zero manual installs); `manage.py backfill_historical` CLI (`--dry-run` + persist via `HistoricalSyncService`); startup env↔DB separation check `config.E001`/`config.E002` (fail-loud on live-settings+`*test*` DB or dev-settings+non-`test`/`dev` DB; pytest harness exempt); `manage.py rule_gate_report` ADR-029 §4 per-rule×regime GO visibility. See `docs/LIVE_READINESS_BLOCKERS.md`. Dev DB convention: `POSTGRES_DB` must carry a `test`/`dev` token (`tradevision_db` now fails E002 under dev settings) |
| Edge Validation (research) | **PENDING real data** | 13 new tests passing | `docs/EDGE_VALIDATION_REPORT.md`: real-data prerequisite PROVEN unmet (10 synthetic candles, no Kite credentials, zero backtest runs); per-rule×regime verdict = INSUFFICIENT-DATA, `validated_regimes` untouched. Built + ground-truth-tested shuffled-baseline significance comparator (`apps/backtesting/domain/significance.py`, 9 known-answer tests) and labeled synthetic pipeline smoke test (walk-forward + cost-sensitivity + significance wiring, 4 PASS/FAIL tests). Cannot be completed until years of real Zerodha/vendor data are backfilled (§7 of the report) |
| Risk Sophistication & Execution Realism | **COMPLETE** | 66 new tests passing (zero new failures vs baseline) | `docs/RISK_SOPHISTICATION_BATCH.md`: portfolio concentration/correlation check (fail-closed, disabled by default); auto drawdown kill switch (audit proved no auto trigger existed; daily breaker live, weekly blocked on missing 7-day P&L source); NSE cost model opt-in (`BACKTEST_COST_MODEL="nse"`); per-rule calibration-drift Celery task (JournalEntry live outcomes vs backtest expectation); `ALGO_REGISTRATION_ID` live gate (`execution.E003` + broker `LIVE_UNREACHABLE_NO_ALGO_REGISTRATION`); `pipeline_health` index rename (hygiene — refuted as a migrate blocker) |

### Phase 0 Deliverables (Completed)

- Docker stack (PostgreSQL, Redis, Celery, Backend) — `infra/docker-compose.yml`
- Django settings (base, development, production, testing) — `config/settings/`
- Custom User model (UUID pk, email auth, roles) — `apps/accounts/models.py`
- JWT authentication endpoints — `apps/accounts/urls.py`
- Health check endpoints (liveness, readiness, db, cache, celery) — `apps/health/`
- BaseModel (UUID, timestamps, soft-delete) — `core/models.py` + `apps/common/models.py`
- Management commands (wait_for_db, wait_for_redis, system_check, seed_admin) — `apps/common/management/commands/`
- AI provider interface + Gemini + 3 stubs — `core/ai/`
- Market data provider interface + MockProvider — `core/market_data/`
- Rule engine registry — `core/rules/rule_registry.py`
- Circuit breaker (Redis-backed) — `core/resilience/circuit_breaker.py`
- Market calendar (NSE) — `core/market_calendar.py`
- Structured logging (structlog + JSON) — `core/logging.py`
- Prometheus metrics definitions — `core/metrics.py`
- Correlation ID middleware — `core/middleware.py`
- Centralised config wrapper — `core/config.py`
- Generic repository ABC — `core/repository.py`
- BaseService + BaseTask — `core/services.py`, `core/tasks/base.py`
- Structural protocols — `core/protocols.py`
- Core test suite — 17 test files, 206 tests passing

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Full Processing Pipeline](#2-full-processing-pipeline)
3. [Major Modules](#3-major-modules)
4. [Market Intelligence Engine](#4-market-intelligence-engine)
5. [Pattern Engine](#5-pattern-engine)
6. [Trader Memory](#6-trader-memory)
7. [AI Architecture](#7-ai-architecture)
8. [Rule Engine](#8-rule-engine)
9. [Backend Architecture](#9-backend-architecture)
10. [Frontend Architecture](#10-frontend-architecture)
11. [Notification Architecture](#11-notification-architecture)
12. [Docker Architecture](#12-docker-architecture)
13. [Folder Structure](#13-folder-structure)
14. [Data Flow](#14-data-flow)
15. [Security Architecture](#15-security-architecture)
16. [Observability and Monitoring](#16-observability-and-monitoring)
17. [Testing Strategy](#17-testing-strategy)
18. [Backup and Recovery](#18-backup-and-recovery)
19. [Deployment Strategy](#19-deployment-strategy)
20. [AI Governance](#20-ai-governance)
21. [Development Roadmap](#21-development-roadmap)
22. [Architecture Decision Records](#22-architecture-decision-records)

---

## 1. System Overview

### 1.1 Vision

TradeVision AI is an AI-powered market intelligence and decision-support platform for the Indian stock market. It is not an automated trading bot. It is an intelligent financial mentor that continuously monitors the market, understands what is happening, explains why it is happening, warns about important events, and provides evidence-based, explainable recommendations.

The platform helps a trader think like an experienced professional — not blindly follow signals.

### 1.2 Architectural Style

**Layered monolith with event-driven internals.**

- Single Django codebase with strict internal Clean Architecture layering
- Event-driven background processing via Celery + Redis
- Real-time delivery via Django Channels + WebSocket
- All state in PostgreSQL (relational + TimescaleDB time-series)
- Internal boundaries enforced by code discipline — splittable into services later if scale demands it

### 1.3 Core Design Principles

| Principle | Statement |
|---|---|
| Rule engine before AI | Monitoring is deterministic. AI is invoked only when a rule fires. |
| Intelligence before reasoning | All data sources are assembled into one clean context before the AI sees anything. |
| AI receives structured data only | The AI layer is never asked to fetch, monitor, or search for data. |
| Business logic in services | Django views are thin HTTP adapters. All logic is in the service layer. |
| Provider interfaces everywhere | AI providers and market data providers are behind abstract interfaces. Swapping is a config change, not a code change. |
| Idempotency by default | Every Celery task with side effects is idempotent. Duplicate executions are safe. |
| Freshness before evaluation | The rule engine validates data freshness before evaluating any symbol. |
| Fail loudly, degrade gracefully | Silent failures are more dangerous than crashes. Circuit breakers, staleness alerts, and budget limits enforce this. |

---

## 2. Full Processing Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                    EXTERNAL DATA SOURCES                     │
│  NSE/BSE Market Feeds · News APIs · Corporate Filings       │
│  Global Indices · Macro Calendars · Options Data            │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│              INGESTION LAYER (Celery + Connectors)           │
│  MarketDataProvider interface (swappable vendors)           │
│  Market calendar awareness (no off-hours polling)           │
│  Circuit breakers on every external call                    │
│  Idempotent upsert into storage                             │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│              PROCESSING LAYER (Parallel Pipelines)           │
│                                                              │
│  ┌─────────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ Technical Engine│  │ Options Eng. │  │ Market Breadth│  │
│  │ RSI,MACD,BB,VWAP│  │ OI,PCR,Greeks│  │ A/D,Sectors   │  │
│  └────────┬────────┘  └──────┬───────┘  └───────┬───────┘  │
│           │                  │                   │          │
│  ┌────────┴──────┐  ┌────────┴──────┐  ┌────────┴──────┐   │
│  │  Global Mkts  │  │  News Engine  │  │  Announcements│   │
│  │  FII,Macro,FX │  │  NLP,Sentiment│  │  BSE/NSE filings│  │
│  └────────┬──────┘  └────────┬──────┘  └────────┬──────┘   │
└───────────┼──────────────────┼──────────────────┼──────────┘
            │                  │                   │
            └──────────────────┼───────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│            MARKET INTELLIGENCE ENGINE (New Core Layer)       │
│                                                              │
│  Assembles all processed signals into one IntelligencePacket│
│  per symbol — a single, clean, structured context object.   │
│                                                              │
│  Inputs:  Price · Volume · Indicators · Options · Breadth   │
│           News · Announcements · Global · FII · Macro       │
│  Output:  IntelligencePacket(symbol, timestamp, all_context) │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│                  PATTERN ENGINE (Phase 6+)                   │
│  Finds historical days similar to today's IntelligencePacket│
│  Scores similarity · Surfaces analogues to AI as context    │
│  "Today resembles 17 Mar 2024 at 87% — BankNifty reversed" │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│                      RULE ENGINE                             │
│  Evaluates IntelligencePacket against deterministic rules   │
│  Validates data freshness before every evaluation           │
│  Outputs: AnalysisEvent (structured, typed) or nothing      │
│  Rules: PriceMovement · VolumeSpike · Breakout · Circuit    │
│         Announcement · Institutional · Macro · MultiEvent   │
└────────────┬────────────────────────────────────────────────┘
             │ Only when a rule fires
             ▼
┌─────────────────────────────────────────────────────────────┐
│                   AI ORCHESTRATOR                            │
│  Receives: AnalysisEvent + IntelligencePacket               │
│  Selects prompt template by event type                      │
│  Calls AIProvider interface (Gemini → Claude/OpenAI/Ollama) │
│  Validates response (Pydantic schema + sanity checks)       │
│  Enforces rate limits, deduplication window, cost budget    │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│               RECOMMENDATION ENGINE                          │
│  Typed AIRecommendation stored with full audit trail        │
│  Mandatory disclaimer attached                              │
│  Confidence floor enforced (below threshold → not delivered)│
│  Stored in Trader Memory for calibration and retrieval      │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│               NOTIFICATION ENGINE                            │
│  WebSocket (Django Channels) · In-app · Email · Push        │
│  Per-user preferences · Quiet hours · Deduplication        │
└────────────┬────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│               DASHBOARD / FRONTEND                           │
│  React · TypeScript · Tailwind · TradingView Charts         │
│  Real-time WebSocket updates                                │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Major Modules

| Module | App Name | Layer | Responsibility |
|---|---|---|---|
| Market Data | `market_data` | Ingestion | Historical + real-time OHLCV, tick storage (TimescaleDB) |
| Technical Analysis | `technical_analysis` | Processing | RSI, MACD, BB, VWAP, ATR, S/R, volume profile |
| Options Chain | `options_chain` | Processing | OI, PCR, max pain, Greeks, unusual activity |
| Market Breadth | `market_breadth` | Processing | A/D ratio, sector rotation, market internals |
| News Engine | `news_feed` | Processing | Aggregation, NLP, entity tagging, materiality scoring |
| Announcements | `announcements` | Processing | BSE/NSE filings, earnings, bulk/block deals, promoter activity |
| Global Markets | `global_markets` | Processing | Global indices, FII/DII flows, USD/INR, crude oil, macro calendar |
| **Market Intelligence Engine** | `intelligence` | **Aggregation** | **Assembles all processed signals into IntelligencePacket per symbol** |
| **Pattern Engine** | `pattern_engine` | **Similarity** | **Historical day matching, similarity scoring, analogue retrieval** |
| Rule Engine | `rule_engine` | Detection | Deterministic event detection against IntelligencePacket |
| AI Engine | `ai_engine` | Reasoning | Provider-agnostic AI orchestration, prompt management, versioned prompt governance, confidence evaluation |
| Strategy Registry | `strategy_registry` | Matching | Deterministic event-to-strategy matching via TradingStrategy model with symbol/sector filters, preferred_provider hints, configurable thresholds |
| Recommendation Engine | `recommendations` | Output | Recommendation lifecycle, explanation composition, delivery |
| **Trader Memory** | `trader_memory` | **Intelligence Store** | **Full recommendation history with context, outcome, calibration** |
| Risk Analysis | `risk_analysis` | Assessment | Volatility, position sizing, scenario analysis, veto flags |
| Backtesting | `backtesting` | Evaluation | Historical signal replay, accuracy tracking |
| Watchlist | `watchlist` | User | Symbol tracking, per-symbol alert configuration |
| Portfolio | `portfolio` | User | Positions, P&L, exposure, drawdown alerts |
| Notifications | `notifications` | Delivery | In-app, WebSocket, email, push, preferences |
| Accounts | `accounts` | Auth | JWT auth, roles, rate limiting, session security |
| Audit Log | `audit_log` | Compliance | Immutable trail for all recommendations, AI calls, user actions |

---

## 4. Market Intelligence Engine

### 4.1 Purpose

The Market Intelligence Engine is the aggregation layer between all data processors and the Rule Engine. Its sole job is to assemble every available signal for a symbol into a single, clean, consistent `IntelligencePacket` object. This ensures:

- The rule engine evaluates complete context, not fragmented signals
- The AI always receives one structured input, not scattered data from multiple sources
- Data quality validation happens once, centrally, before anything downstream acts on it
- Adding a new data source (e.g., social sentiment) only requires updating the IntelligencePacket assembly — nothing else changes

### 4.2 IntelligencePacket Structure

```
IntelligencePacket
├── symbol: str
├── timestamp: datetime
├── freshness_validated: bool
├── price_context
│   ├── current_price, open, high, low, prev_close
│   ├── change_pct, volume, avg_volume_20d
│   └── circuit_status (NORMAL / UPPER / LOWER)
├── technical_context
│   ├── rsi_14, macd, macd_signal, macd_hist
│   ├── bb_upper, bb_lower, bb_width
│   ├── vwap, atr_14
│   ├── support_levels[], resistance_levels[]
│   └── trend: (UPTREND / DOWNTREND / SIDEWAYS)
├── options_context (nullable)
│   ├── pcr, max_pain, atm_iv
│   ├── unusual_activity: bool
│   └── oi_change_pct
├── breadth_context
│   ├── sector_index_change_pct
│   ├── sector_advance_decline
│   └── nifty_change_pct, sensex_change_pct
├── news_context
│   ├── headlines[]: [{title, source, sentiment, materiality, age_minutes}]
│   └── aggregate_sentiment: (POSITIVE / NEGATIVE / NEUTRAL / MIXED)
├── announcement_context (nullable)
│   ├── recent_announcements[]: [{type, title, materiality, age_hours}]
│   └── pending_events[]: [{type, scheduled_at}]
├── global_context
│   ├── dow_futures_pct, sgx_nifty_pct
│   ├── crude_oil_pct, usdINR_change_pct
│   ├── vix, india_vix
│   └── fii_net_flow_cr (today)
├── institutional_context (nullable)
│   ├── bulk_deals[]: [{entity, quantity, price, side}]
│   └── block_deals[]: [{entity, quantity, price, side}]
├── pattern_context (nullable — populated by Pattern Engine)
│   ├── similar_historical_dates[]: [{date, similarity_score, outcome}]
│   └── top_analogue_summary: str
└── data_quality
    ├── missing_sources[]: list of sources not available
    ├── stale_sources[]: list of sources beyond freshness threshold
    └── quality_score: float (0.0–1.0)
```

### 4.3 Assembly Logic

The IntelligencePacket is assembled by `IntelligenceService.build_packet(symbol)`:
1. Query each processing layer's latest stored output for the symbol
2. Validate freshness of each source (staleness threshold per source type)
3. Compute `data_quality` score based on available vs. expected sources
4. If `quality_score` < configurable threshold, attach `DATA_QUALITY_WARNING` flag
5. Return complete packet — never raise an exception for missing optional sources; mark them as unavailable in `data_quality.missing_sources`

### 4.4 When It Is Called

- After every market data ingestion cycle (triggers the full pipeline per symbol)
- On-demand when an announcement or news event fires (forces immediate packet rebuild for affected symbol)
- On-demand from the Rule Engine's manual trigger API (admin use)

---

## 5. Pattern Engine

### 5.1 Purpose

The Pattern Engine finds historical trading days that are structurally similar to the current `IntelligencePacket` for a symbol. It scores similarity deterministically and provides the AI with real historical analogues — not speculation.

Example output to AI: *"Today's setup for RELIANCE resembles 17 March 2024 at 87% similarity. On that day: price had fallen 2.9%, crude was up 3.1%, FII sold ₹1,200 Cr. BankNifty reversed at 11:30 AM after testing the 200 DMA. Final day close: +0.4%."*

This is powerful and fully deterministic — the AI interprets it, but the Pattern Engine generates it without LLM involvement.

### 5.2 Similarity Scoring

Similarity is computed as a weighted vector distance across a defined feature set:

| Feature Group | Features Used | Weight |
|---|---|---|
| Price action | Change %, gap %, volume ratio | 30% |
| Technical state | RSI, MACD histogram, BB position, trend | 25% |
| Options | PCR, OI change direction | 15% |
| Macro/Global | Nifty %, crude %, FII net flow direction | 20% |
| Breadth | Sector trend direction, A/D ratio | 10% |

Cosine similarity or Euclidean distance on the normalized feature vector. Top N similar days returned (configurable, default: 5), with similarity score and actual subsequent price outcomes.

### 5.3 When It Is Called

- Called by `IntelligenceService.build_packet()` as an optional enrichment step
- Only triggered when the Rule Engine has flagged the symbol (not on every tick — expensive)
- Results stored in `pattern_context` within the IntelligencePacket
- Historical feature vectors precomputed nightly (not computed at query time)

### 5.4 Phase

Pattern Engine is not Phase 0. It is introduced in **Phase 6** after the core intelligence pipeline is stable and a meaningful historical dataset has been accumulated.

---

## 6. Trader Memory

### 6.1 Purpose

Trader Memory is the system's institutional knowledge store. Every recommendation the system generates — along with the full context that generated it, the AI's reasoning, and eventually the real market outcome — is stored in a structured, queryable, and retrievable form.

Over time, Trader Memory enables:
- Accuracy reports: was the AI right?
- Confidence calibration: is 80% confidence actually 80% accurate?
- Prompt improvement: which prompt versions perform best in which market conditions?
- Retrieval-augmented generation: feed similar past cases to the AI as additional context
- Regulatory auditability: full trail of every recommendation with its basis

### 6.2 Trader Memory Record Structure

```
TraderMemoryRecord
├── id: UUID
├── created_at: datetime
├── symbol: str
├── event_type: str                    # Which rule fired
├── prompt_version: str                # e.g., "v2.3" — tracks which prompt was used
├── ai_provider: str                   # e.g., "gemini-1.5-pro"
├── intelligence_packet: JSON          # Full IntelligencePacket snapshot at time of call
├── prompt_rendered: str               # Exact prompt sent to AI (for audit + replay)
├── ai_raw_response: str               # Raw AI output before parsing
├── recommendation
│   ├── direction: BUY | SELL | WATCH | AVOID
│   ├── confidence_score: float
│   ├── reasoning: str
│   ├── risk_assessment: LOW | MEDIUM | HIGH | VERY_HIGH
│   ├── risk_explanation: str
│   ├── key_factors: list[str]
│   ├── contradicting_factors: list[str]
│   ├── time_horizon: SHORT | MEDIUM | LONG
│   └── follow_up_triggers: list[str]
├── delivery
│   ├── delivered_to_users: list[UUID]
│   ├── delivered_at: datetime
│   ├── suppressed: bool               # True if confidence below floor
│   └── suppression_reason: str
└── outcome                            # Populated by backtesting module later
    ├── status: PENDING | CORRECT | INCORRECT | PARTIAL | INCONCLUSIVE
    ├── actual_price_change_pct: float
    ├── evaluation_window_hours: int
    ├── evaluated_at: datetime
    └── evaluator_notes: str
```

### 6.3 How Outcome Is Tracked

The backtesting module runs nightly and evaluates all `PENDING` Trader Memory records whose evaluation window has passed:
- Fetch the price N hours after the recommendation was generated
- Compare direction (was BUY followed by price increase?) against a configurable threshold
- Mark `CORRECT`, `INCORRECT`, or `PARTIAL`
- Aggregate accuracy per `prompt_version`, per `event_type`, per `ai_provider`, per market regime

### 6.4 Confidence Calibration

A calibration report computes: for all recommendations with confidence in range [0.8, 0.85], what was the actual accuracy rate? A well-calibrated system should show ~82%. Significant deviation triggers a prompt review flag. This calibration data is also surfaced in the admin dashboard.

### 6.5 RAG Integration (Phase 7+)

Once Trader Memory contains sufficient records (target: 500+), the Pattern Engine's similar historical dates can be enriched with actual past Trader Memory records: *"On 17 March 2024, the AI recommended WATCH with 0.71 confidence. Outcome: CORRECT. Reasoning: [excerpt]."* This closes the loop between historical pattern detection and AI-informed past outcomes.

---

## 7. AI Architecture

### 7.1 Provider Interface

All AI providers implement a single abstract interface in `core/ai/base_provider.py`. Business logic never imports a concrete provider. The `AIProviderFactory` reads `settings.AI_PROVIDER` and returns the appropriate implementation.

Supported providers (implementation status):
- `GeminiProvider` — active (Phase 4)
- `OpenAIProvider` — stubbed (wire in when needed)
- `ClaudeProvider` — stubbed (wire in when needed)
- `OllamaProvider` — stubbed (local LLM option)

### 7.2 Prompt Library

All prompts are versioned Jinja2 templates in `core/ai/prompts/`. Never hardcoded in business logic. Version string tracked in every Trader Memory record.

| Template | Trigger |
|---|---|
| `price_movement.j2` | Significant price move detected |
| `volume_spike.j2` | Volume spike detected |
| `breakout.j2` | Technical breakout or breakdown |
| `announcement.j2` | High-materiality corporate announcement |
| `earnings.j2` | Quarterly results |
| `institutional_activity.j2` | Bulk/block deal or FII flow |
| `macro_event.j2` | Macro event with sector impact |
| `multi_event.j2` | Multiple concurrent events on same symbol |

### 7.3 AI Governance Controls

| Control | Mechanism |
|---|---|
| Rate limiting | Redis counter before every AI call |
| Deduplication window | Same symbol + same event type suppressed within 5 min |
| Cost budget | Hard daily/monthly limit in Redis; soft warning at 80% |
| Confidence floor | Recommendations below threshold stored but not delivered |
| Response validation | Pydantic schema + sanity checks in `ai_engine/validators.py` |
| Mandatory disclaimer | Attached to every delivered recommendation; non-removable |
| Output drift monitoring | Daily distribution check on direction + confidence distribution |
| Graceful degradation | AI outage → event queued; system notifies user "analysis pending" |

### 7.4 Response Validation

Every AI response passes through `AIResponseValidator` before persisting:
- Pydantic schema validation (required fields, type correctness, range checks)
- Confidence in [0.0, 1.0]
- Hallucination signal check: confidence > 0.85 with zero contradicting factors → flagged
- Data sufficiency check: if `intelligence_packet.data_quality.quality_score` < threshold → `DATA_INSUFFICIENT` flag attached regardless of AI output
- Liquidity check: illiquid symbols (avg volume < configurable threshold) → liquidity warning attached

---

## 8. Rule Engine

### 8.1 Design

- Evaluates `IntelligencePacket` objects (never raw data directly)
- Validates data freshness before any evaluation (staleness threshold per symbol)
- Each rule is an independent class implementing `BaseRule`
- Rules registered in `RuleRegistry` — discoverable, configurable via database
- Rule thresholds stored in database, admin-editable without code deploy
- Every evaluation logged in `RuleExecution` model (fired/no-fire, which data triggered)

### 8.2 Initial Rule Set

| Rule | Trigger Condition |
|---|---|
| `PriceMovementRule` | Price change > N% in M minutes |
| `VolumeSpikeRule` | Volume > N × 20-day average |
| `BreakoutRule` | Price crosses resistance (above) or support (below) |
| `BreakdownRule` | Price closes below key moving average |
| `CircuitBreakerRule` | Upper or lower circuit hit |
| `GapMovementRule` | Opening gap > N% from previous close |
| `AnnouncementRule` | Materiality score >= HIGH from announcements module |
| `InstitutionalActivityRule` | Bulk/block deal above configurable value threshold |
| `MacroEventRule` | Macro event with HIGH sector impact flagged |
| `MultiEventRule` | 2+ distinct rules fire on same symbol within 15 min |

### 8.3 Freshness Guard

Before evaluating any symbol, the Rule Engine checks:
- Latest tick age <= 2 minutes (during market hours)
- Key indicator age <= 5 minutes
- If stale: skip evaluation, publish `STALE_DATA` event, log warning — never evaluate on stale data

---

## 9. Backend Architecture

### 9.1 Layering (Strictly Enforced)

```
View / Consumer / Celery Task
    → Serializer (shape only, no logic)
        → Service (all business logic)
            → Repository (all DB queries)
                → Model (schema + field validation only)
```

Higher layers never import from lower layers. Services never import from views. Models have no business methods.

### 9.2 Celery Queues

| Queue | Workers | Task Types |
|---|---|---|
| `market_data` | High concurrency | Tick ingestion, OHLCV polling |
| `processing` | CPU-optimized | Indicator computation, NLP, options analysis |
| `intelligence` | Moderate | IntelligencePacket assembly per symbol |
| `rule_engine` | Moderate | Rule evaluation |
| `ai` | Rate-limited (matches provider limits) | AI provider calls |
| `notifications` | High concurrency | WebSocket push, email, push delivery |
| `analytics` | Low concurrency | Backtesting, calibration, EOD aggregation |
| `default` | General | Miscellaneous |

### 9.3 Database Architecture

| Store | Technology | Data |
|---|---|---|
| Relational | PostgreSQL 16 | Users, portfolios, watchlists, rules, recommendations, audit logs |
| Time-series | TimescaleDB (PG extension) | OHLCV bars, tick data, computed indicators, IntelligencePacket snapshots |
| Cache | Redis 7 | Hot data, session state, rate limit counters, circuit breaker state |
| Queue | Redis 7 | Celery broker, Channels layer, event bus (Streams), Pub/Sub (notifications) |

### 9.4 Critical Backend Additions (from Architecture Review)

**Circuit Breaker:** `core/resilience/circuit_breaker.py` — wraps every external API call. After N failures, circuit opens, `FEED_DEGRADED` notification published, half-open probe interval before retry.

**Idempotency:** All ingestion tasks use upsert (`INSERT ... ON CONFLICT DO NOTHING` for TimescaleDB). All AI tasks check for existing recommendation against `AnalysisEvent.id` before calling provider.

**Market Calendar:** `core/market_calendar.py` — all market-data Celery tasks check calendar status before executing. Pre-market, market hours, post-market, and holiday states handled explicitly.

**Connection Pooling:** `pgbouncer` container in transaction-mode pooling between application containers and PostgreSQL. Django `CONN_MAX_AGE` configured as interim measure.

**Celery Task Result Expiry:** `result_expires = 3600` (1 hour) — prevents Redis memory exhaustion from accumulated task results.

**API Versioning:** All endpoints under `/api/v1/` from Phase 1. Never change this prefix — client compatibility depends on it.

**Soft Delete:** `watchlist`, `portfolio`, `recommendations`, `trader_memory` use `is_deleted` + `deleted_at` — never hard DELETE.

---

## 10. Frontend Architecture

### 10.1 Stack

React 18 · TypeScript · Tailwind CSS · TradingView Lightweight Charts · React Query (TanStack) · Zustand · Axios

### 10.2 State Management

| State Type | Tool |
|---|---|
| Server state | React Query — caching, background refetch, invalidation |
| Global UI state | Zustand — auth, theme, sidebar, notification count |
| Real-time streaming | Custom hooks over WebSocket client |
| Local component state | `useState` / `useReducer` |

### 10.3 Pages

| Page | Real-time? |
|---|---|
| Dashboard | Yes — live quotes, recommendations, alerts |
| Stock Detail | Yes — price, new recommendations, news |
| Watchlist | Yes — live quotes per symbol |
| Recommendations | No — periodic refresh |
| Trader Memory / History | No |
| Portfolio | Semi-real-time |
| Notifications | Yes |
| Settings | No |

### 10.4 WebSocket Architecture

Singleton `WebSocketClient` in `src/sockets/`. Named subscription hooks per stream type. All reconnection logic centralized. WebSocket auth via short-lived token in upgrade handshake (not long-lived JWT in query param — see Section 15).

---

## 11. Notification Architecture

### 11.1 Notification Types

| Type | Trigger | Channels |
|---|---|---|
| `RECOMMENDATION` | Rule fired + AI completed | WS + in-app + email (optional) |
| `PRICE_ALERT` | User price threshold crossed | WS + in-app |
| `ANNOUNCEMENT` | High-materiality filing | WS + in-app + email (optional) |
| `EARNINGS` | Pre-alert + results published | WS + in-app + email |
| `CIRCUIT` | Circuit breaker hit on watched symbol | WS + in-app |
| `MACRO_EVENT` | Scheduled macro event | In-app |
| `PORTFOLIO_ALERT` | Drawdown threshold, expiry warning | WS + in-app |
| `FEED_DEGRADED` | Circuit breaker opened on data source | In-app (admin) |
| `AI_BUDGET_WARNING` | AI cost at 80% of daily limit | In-app (admin) |
| `STALE_DATA` | Symbol data beyond freshness threshold | In-app (admin) |
| `SYSTEM` | Service health issues | In-app (admin) |

### 11.2 Delivery Flow

```
Event occurs
↓
NotificationService.create(user_id, type, payload)
↓
Persisted in PostgreSQL (is_read=False)
↓
Celery task: publish to Redis channel layer
↓
Django Channels → user's personal WS group ("notifications.{user_id}")
↓
Frontend Zustand store updated → UI renders in real-time
```

### 11.3 User Groups (Channels)

- `notifications.{user_id}` — personal alerts, recommendations, system messages
- `market.{symbol}` — live price updates for symbols on active watchlist/page
- `admin.system` — operational alerts (feed degraded, budget warning, stale data)

---

## 12. Docker Architecture

### 12.1 Container Inventory

| Container | Base | Role |
|---|---|---|
| `backend` | python:3.12-slim | Django ASGI app (Daphne) |
| `celery-worker-market` | Same as backend | Market data + intelligence queues |
| `celery-worker-ai` | Same as backend | AI queue (rate-limited pool) |
| `celery-worker-default` | Same as backend | Notifications + analytics + default |
| `celery-beat` | Same as backend | Periodic task scheduler |
| `frontend` | node:20-alpine → nginx:alpine | React build + static serving |
| `nginx` | nginx:alpine | Reverse proxy, TLS termination, routing |
| `postgres` | timescale/timescaledb:latest-pg16 | PostgreSQL + TimescaleDB |
| `pgbouncer` | pgbouncer:latest | Connection pooler (between app and postgres) |
| `redis` | redis:7-alpine | Cache + Celery broker + Channels layer |
| `flower` | mher/flower | Celery monitoring (dev + staging only) |

### 12.2 Networks

| Network | Members | Purpose |
|---|---|---|
| `edge` | `nginx`, `frontend`, `backend` | Public-facing traffic |
| `app` | `backend`, all `celery-*`, `pgbouncer`, `redis` | Internal application traffic |
| `data` | `pgbouncer`, `postgres`, `redis` | Database tier |
| `monitoring` | `flower`, `backend`, all `celery-*` | Ops visibility |

`postgres` is never directly on the `app` network — all app connections go through `pgbouncer`.

### 12.3 Volumes

| Volume | Mounted By | Backup Priority |
|---|---|---|
| `postgres-data` | `postgres` | Critical |
| `redis-data` | `redis` | Medium (AOF for broker, RDB for cache) |
| `static-files` | `backend`, `nginx` | Low (rebuildable) |
| `media-files` | `backend`, `nginx` | Medium |

### 12.4 Compose Strategy

- `docker-compose.yml` — base definitions
- `docker-compose.dev.yml` — bind mounts, Flower exposed, debug ports, hot reload, relaxed limits
- `docker-compose.prod.yml` — resource limits, production image tags, no debug ports, TLS

### 12.5 Dev vs Production

| Concern | Development | Production |
|---|---|---|
| Source code | Bind-mounted | Baked into image |
| Secrets | `.env.local` (git-ignored) | Injected at runtime via CI/CD |
| TLS | HTTP only | TLS enforced at Nginx |
| Celery workers | Single combined worker | Separate containers per queue |
| Flower | Exposed | Not deployed |
| Resource limits | None | Explicitly set |
| Log level | DEBUG | INFO |
| Redis AOF | Disabled | Enabled for broker data |

---

## 13. Folder Structure

```
tradevision/
│
├── backend/
│   ├── config/
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   ├── production.py
│   │   │   └── testing.py
│   │   ├── urls.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   │
│   ├── apps/
│   │   ├── market_data/
│   │   │   ├── models.py
│   │   │   ├── repository.py
│   │   │   ├── services.py
│   │   │   ├── tasks.py
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   ├── urls.py
│   │   │   ├── consumers.py
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── migrations/
│   │   │   └── tests/
│   │   │       ├── test_models.py
│   │   │       ├── test_services.py
│   │   │       ├── test_tasks.py
│   │   │       └── test_api.py
│   │   │
│   │   ├── technical_analysis/
│   │   ├── options_chain/
│   │   ├── market_breadth/
│   │   ├── news_feed/
│   │   ├── announcements/
│   │   ├── global_markets/
│   │   ├── intelligence/             # Market Intelligence Engine
│   │   ├── pattern_engine/           # Pattern Engine (Phase 6+)
│   │   ├── rule_engine/
│   │   ├── ai_engine/
│   │   ├── recommendations/
│   │   ├── strategy_registry/        # Strategy Registry (B.3)
│   │   ├── trader_memory/            # Trader Memory
│   │   ├── risk_analysis/
│   │   ├── backtesting/
│   │   ├── watchlist/
│   │   ├── portfolio/
│   │   ├── notifications/
│   │   ├── accounts/
│   │   └── audit_log/
│   │
│   ├── core/                         # Shared — no models, no migrations
│   │   ├── ai/
│   │   │   ├── base_provider.py      # Abstract AI provider interface
│   │   │   ├── gemini_provider.py
│   │   │   ├── openai_provider.py    # Stubbed
│   │   │   ├── claude_provider.py    # Stubbed
│   │   │   ├── ollama_provider.py    # Stubbed
│   │   │   ├── provider_factory.py
│   │   │   └── prompts/
│   │   │       ├── price_movement.j2
│   │   │       ├── volume_spike.j2
│   │   │       ├── breakout.j2
│   │   │       ├── announcement.j2
│   │   │       ├── earnings.j2
│   │   │       ├── institutional_activity.j2
│   │   │       ├── macro_event.j2
│   │   │       └── multi_event.j2
│   │   ├── market_data/
│   │   │   ├── base_provider.py      # Abstract market data provider interface
│   │   │   └── provider_factory.py
│   │   ├── resilience/
│   │   │   └── circuit_breaker.py
│   │   ├── events/
│   │   │   ├── event_types.py        # AnalysisEvent, IntelligencePacket dataclasses
│   │   │   └── event_bus.py          # Redis Streams wrapper (AnalysisEvent transport, ADR-013)
│   │   ├── rules/
│   │   │   ├── base_rule.py
│   │   │   └── rule_registry.py
│   │   ├── market_calendar.py        # Trading hours, holidays, session states
│   │   ├── exceptions.py
│   │   ├── logging.py                # Structured JSON logging factory
│   │   ├── metrics.py                # Prometheus metrics definitions
│   │   ├── pagination.py
│   │   ├── permissions.py
│   │   └── utils.py
│   │
│   ├── manage.py
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── development.txt
│   │   └── production.txt
│   └── pytest.ini
│
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   │   ├── ui/
│   │   │   ├── charts/
│   │   │   ├── market/
│   │   │   ├── intelligence/
│   │   │   ├── recommendations/
│   │   │   ├── trader_memory/
│   │   │   ├── notifications/
│   │   │   └── portfolio/
│   │   ├── pages/
│   │   │   ├── Dashboard/
│   │   │   ├── Stock/
│   │   │   ├── Watchlist/
│   │   │   ├── Recommendations/
│   │   │   ├── TraderMemory/
│   │   │   ├── Portfolio/
│   │   │   └── Settings/
│   │   ├── hooks/
│   │   ├── stores/
│   │   ├── sockets/
│   │   ├── types/
│   │   ├── utils/
│   │   └── App.tsx
│   ├── package.json
│   ├── tsconfig.json
│   └── tailwind.config.ts
│
├── infra/
│   ├── docker/
│   │   ├── backend/
│   │   │   ├── Dockerfile.dev
│   │   │   └── Dockerfile.prod
│   │   ├── frontend/
│   │   │   ├── Dockerfile.dev
│   │   │   └── Dockerfile.prod
│   │   └── nginx/
│   │       ├── nginx.dev.conf
│   │       └── nginx.prod.conf
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   ├── docker-compose.prod.yml
│   └── scripts/
│       ├── entrypoint.backend.sh
│       └── entrypoint.celery.sh
│
├── docs/
│   ├── architecture/
│   │   └── v1.0.md                   # This document
│   ├── adr/
│   │   ├── ADR-001-monolith-first.md
│   │   ├── ADR-002-rule-engine-before-ai.md
│   │   ├── ADR-003-ai-provider-interface.md
│   │   ├── ADR-004-timescaledb-for-ticks.md
│   │   ├── ADR-005-market-intelligence-engine.md
│   │   ├── ADR-006-trader-memory.md
│   │   └── ADR-007-pattern-engine-phase-6.md
│   ├── operations/
│   │   ├── secret_rotation.md
│   │   ├── backup_recovery.md
│   │   └── deployment_runbook.md
│   └── api/
│       └── openapi.yaml
│
└── scripts/
    ├── seed_data.py
    └── load_historical_data.py
```

---

## 14. Data Flow

### 14.1 Real-Time Monitoring Flow

```
1. INGESTION (every 1 min, market hours only)
   Celery Beat fires → MarketDataService.fetch_and_store(symbol)
   → Data freshness validated on response
   → Upserted into TimescaleDB (idempotent)
   → Redis pub/sub: "tick.{symbol}" published

2. PROCESSING (triggered by tick event)
   TechnicalAnalysisService.compute(symbol) → stored in TimescaleDB
   Parallel (if configured): OptionsService, BreadthService update

3. INTELLIGENCE ASSEMBLY
   IntelligenceService.build_packet(symbol)
   → Queries all processing layer outputs
   → Validates freshness per source
   → Computes data_quality score
   → Returns IntelligencePacket

4. RULE ENGINE
   RuleEngine.evaluate(packet)
   → Freshness guard (aborts if stale)
   → Evaluates all registered rules
   → If no rule fires: loop ends
   → If rule fires: AnalysisEvent created + dispatched

5. AI ORCHESTRATION (only on AnalysisEvent)
   Rate limit check → deduplication check → budget check
   ContextBuilder.build(event, packet) → structured prompt
   PromptBuilder.render(template, context) → final prompt
   AIProvider.complete(prompt) → raw response
   AIResponseValidator.validate(response) → typed AIRecommendation
   RecommendationService.create(event, recommendation)

6. TRADER MEMORY
   TraderMemoryService.record(event, packet, prompt, response, recommendation)
   → Stored with outcome status = PENDING

7. NOTIFICATION
   NotificationService.dispatch(recommendation)
   → Persisted in PostgreSQL
   → Redis channel layer published
   → Django Channels pushes to user WS group
   → Frontend updates in real-time
```

### 14.2 Outcome Tracking Flow (Nightly)

```
Celery Beat: backtesting task (11:00 PM IST daily)
→ Query all TraderMemory records where outcome.status = PENDING
  AND created_at + evaluation_window_hours <= now
→ For each: fetch actual price at evaluation point
→ Compare direction + magnitude against recommendation
→ Mark CORRECT / INCORRECT / PARTIAL
→ Aggregate calibration statistics per prompt_version + event_type
→ Publish calibration report (admin notification if drift detected)
```

---

## 15. Security Architecture

### 15.1 Authentication

- JWT access tokens (short-lived: 15 minutes) + refresh tokens (rotation on use, 7-day absolute expiry)
- Token revocation via Redis blacklist (for logout + suspicious activity)
- Roles: `ADMIN`, `TRADER`, `READ_ONLY` — permissions enforced at view level via DRF permission classes
- Account lockout: 5 failed login attempts → 30-minute lockout (tracked in Redis)
- Rate limiting on `/api/v1/auth/` endpoints: strict (configurable, default: 10 req/min per IP)

### 15.2 WebSocket Authentication

WebSocket upgrade authenticated via short-lived token (separate from access JWT, valid 60 seconds, single-use) exchanged before WebSocket connection is opened. This avoids long-lived credentials in query parameters which are logged by proxies.

### 15.3 Secrets Strategy

- No secrets in version control — only `.env.example` with placeholder values committed
- No secrets baked into Docker images
- Secrets injected at container runtime via CI/CD environment
- Django `SECRET_KEY_FALLBACKS` for zero-downtime key rotation
- AI provider key rotation: new key in settings → deploy → revoke old key (no restart required if loaded from environment)
- Documented rotation schedule per secret class in `docs/operations/secret_rotation.md`

### 15.4 API Security

- Rate limiting: unauthenticated (strict) vs. authenticated (generous) tiers via DRF throttle classes
- CORS: explicit allowlist, no wildcard in production
- All responses include standard security headers via Nginx (HSTS, X-Frame-Options, CSP, X-Content-Type-Options)
- No direct database port exposure from any container to host in production

---

## 16. Observability and Monitoring

### 16.1 Structured Logging

- Format: JSON via `python-json-logger` across all services
- Mandatory fields: `timestamp`, `level`, `module`, `event`, `correlation_id`
- Context fields where applicable: `symbol`, `user_id`, `duration_ms`, `provider`
- Correlation ID (UUID) attached to every request and Celery task, propagated through all child log entries

### 16.2 Log Levels

| Level | Use |
|---|---|
| DEBUG | Indicator values, rule evaluation details (dev/staging only) |
| INFO | Task start/complete, rule fires, AI calls, recommendations created |
| WARNING | Stale data, feed degraded, AI low confidence, budget at 80% |
| ERROR | External API failures, parse failures, circuit breaker opened |
| CRITICAL | DB connectivity lost, Redis lost, complete data feed loss |

### 16.3 Metrics (Prometheus)

| Metric | Type | Labels |
|---|---|---|
| `tradevision_ticks_ingested_total` | Counter | `symbol`, `interval` |
| `tradevision_rule_evaluations_total` | Counter | `rule`, `outcome` |
| `tradevision_ai_calls_total` | Counter | `provider`, `event_type`, `outcome` |
| `tradevision_ai_call_duration_seconds` | Histogram | `provider` |
| `tradevision_ai_cost_usd_total` | Counter | `provider` |
| `tradevision_recommendations_total` | Counter | `direction`, `delivered` |
| `tradevision_celery_task_duration_seconds` | Histogram | `task_name`, `queue` |
| `tradevision_data_freshness_seconds` | Gauge | `symbol`, `source` |
| `tradevision_circuit_breaker_state` | Gauge | `service` (0=closed, 1=open) |
| `tradevision_intelligence_packet_quality` | Histogram | `symbol` |

### 16.4 Alerting Rules

| Alert | Condition | Severity |
|---|---|---|
| Data feed stale | `tradevision_data_freshness_seconds > 300` during market hours | CRITICAL |
| Celery backlog | Queue depth > 500 | WARNING |
| AI error rate | AI call error rate > 10% over 5 min | WARNING |
| AI budget | Cost at 80% of daily limit | WARNING |
| AI budget exhausted | Cost at 100% | CRITICAL |
| Circuit breaker open | Any circuit breaker state = 1 | ERROR |
| DB connection exhausted | pgbouncer wait_count > 10 | CRITICAL |
| Missed Celery Beat task | Task not executed within 2× schedule interval | WARNING |
| Recommendation drift | Direction distribution shifts > 20% vs 30-day baseline | WARNING |

---

## 17. Testing Strategy

### 17.1 Test Types

**Unit tests** — service layer only. All external dependencies (AI provider, data APIs, Celery, DB) mocked. Cover: happy path, every error branch, boundary conditions. Fastest test class — must run in < 30 seconds total.

**Integration tests** — full path from task → service → repository → real PostgreSQL + real TimescaleDB. SQLite is never used in any test — TimescaleDB behavior cannot be simulated. Run in CI against a real database container.

**Contract tests** — every concrete AI provider implementation must pass an identical test suite validating the abstract interface contract. New providers cannot be merged without passing the full contract suite.

**Rule engine test matrix** — every rule has a test matrix: data that must fire, data that must not fire, and exact boundary values. These are the most business-critical tests.

**API tests** — DRF test client against real endpoints. Auth, permissions, pagination, error responses.

**Research integrity suite** (`backend/tests/research_integrity/`, 17 tests) — adversarial datasets replayed through the REAL event chain (TA ingestion → event bus → intelligence → rule_engine → risk_management → execution → paper broker) to prove the backtesting pipeline leaks no future information: same-candle execution, look-ahead fill fallback, out-of-range future data, IS/OOS split keyed on simulated fill time (not wall-clock `order.created_at`), walk-forward per-window account isolation, simulated fill timestamps, and no survivorship-biased universe filter. Both proven defects (IS/OOS wall-clock contamination, `open`→`close` look-ahead fallback) are regression-pinned — the tests fail if the fixes are reverted. See `docs/RESEARCH_INTEGRITY.md`.

### 17.2 Test Infrastructure

- pytest + pytest-django
- Factory Boy for model fixtures (no manual `Model.objects.create()` in tests)
- Curated realistic OHLCV fixture dataset (5 symbols, 30 days) shared across all modules
- Transaction-wrapped DB per test (rollback after each test — no shared state)
- `pytest-cov` with minimum coverage gate: 80% service layer, 70% overall (enforced in CI)
- AI provider always mocked in tests (never real API calls in CI)

### 17.3 CI Gate

All of the following must pass before merge:
- Linting (flake8 / ruff)
- Type checking (mypy — strict mode on `core/`, standard on `apps/`)
- Unit tests
- Integration tests (against real DB containers in CI)
- Coverage gate

### 17.4 Remediation Batch — Environment & Runtime (2026-08-19)

- Local venv rebuilt to the declared Django line (`>=5.0,<5.1` → Django 5.0.14; was 6.0.7); `pip check` clean.
- Migration drift in `recommendations`, `rule_engine`, `signals_engine`, `trader_memory` closed with 4 non-destructive migrations (BaseModel `help_text` drift → no-op `AlterField`s; `Meta.indexes` lacking explicit `name=` → 4 `ALTER INDEX … RENAME`); `makemigrations --check --dry-run` exits 0.
- Reserved-`LogRecord`-attribute logging bug fixed in `prompt_manager._load_templates` (all 11 prompt templates were silently failing to load) plus two same-class instances (`instrument_sync_complete` `created`, DRF exception handler `message`). Regression-pinned by `apps/ai_engine/tests/test_prompt_manager_regression.py` (3 tests, verified to fail against the old bug). See `docs/REMEDIATION_BATCH_ENV_RUNTIME.md`.

---

## 18. Backup and Recovery

### 18.1 PostgreSQL + TimescaleDB

- WAL archiving to separate volume (point-in-time recovery target: 1 hour max data loss)
- Daily `pg_dump` as secondary backup, retained 30 days
- `pgBackRest` for TimescaleDB continuous backup
- Backup success monitored — alert if latest backup is older than 25 hours

### 18.2 Redis

- AOF persistence enabled for broker data (Celery tasks, channel layer)
- RDB snapshots for cache tier (hourly — rebuildable but faster than cold start)
- Redis persistence explicitly configured in compose — Docker default image has persistence off

### 18.3 Recovery Drills

- Quarterly restore drill from backup to staging environment
- Documented runbook in `docs/operations/backup_recovery.md`
- First restore should never happen during an incident

### 18.4 Recovery Time Objectives (Targets)

| Component | RPO (max data loss) | RTO (max downtime) |
|---|---|---|
| PostgreSQL | 1 hour | 2 hours |
| TimescaleDB (tick data) | 1 day (rebuildable from vendor) | 4 hours |
| Redis (broker) | In-flight tasks (< 1 min) | 30 minutes |
| Application containers | 0 (stateless) | 10 minutes |

---

## 19. Deployment Strategy

### 19.1 Zero-Downtime Deploy

- Rolling restart: new container starts → health check passes → old container stops
- Never stop old before new is confirmed healthy
- Backend health check endpoint: `GET /api/v1/health/` returns 200 when DB + Redis are reachable

### 19.2 Database Migration Safety

- Every migration must be backward-compatible with the currently deployed code
- Two-phase migration pattern: add nullable → deploy → backfill → enforce non-null in next deploy
- Never run irreversible migrations without a tested compensating migration prepared first

### 19.3 Celery Worker Drain

- SIGTERM → Celery workers complete in-flight tasks before stopping
- `acks_late = True` on all queues — tasks re-queued if worker dies before acknowledgement
- Never SIGKILL a Celery worker during a deploy

### 19.4 Environment Promotion

```
Development (local, mocked data, bind mounts)
    ↓  build + tag image (git SHA tag)
Staging (sandboxed data, production-like config, same image)
    ↓  promote same image (no rebuild)
Production (live data, full security posture, same image)
```

### 19.5 Rollback

- Every deploy tagged with git SHA — rollback is re-deploying previous SHA tag
- Database rollback: compensating migration deployed (not `migrate --reverse`)
- Rollback procedure documented in `docs/operations/deployment_runbook.md`

---

## 20. AI Governance

| Requirement | Implementation |
|---|---|
| Confidence floor | Below threshold → stored, not delivered. Threshold configurable in settings. |
| Mandatory disclaimer | Non-removable text on every delivered recommendation. Stored in settings, not hardcoded. |
| Prompt versioning | Every prompt change version-tagged. DB-backed persistence with activate/rollback governance (B.2). Trader Memory records which version generated each recommendation. |
| Cost budget | Hard daily limit enforced in Redis before every call. Admin alert at 80%. |
| Output drift monitoring | Nightly distribution check. Admin alert on significant shift. |
| Data quality gate | `IntelligencePacket.data_quality.quality_score` < threshold → `DATA_INSUFFICIENT` flag attached. |
| Hallucination signal | High confidence + zero contradicting factors → flagged for review. |
| Liquidity warning | Illiquid symbols → liquidity warning attached regardless of AI output. |
| Graceful degradation | Provider unavailable → event queued, user notified "analysis pending." |
| Audit trail | Every AI call logged in full: prompt, response, provider, prompt version, token estimate, cost estimate. |

---

## 21. Development Roadmap

| Phase | Focus | Key Deliverable |
|---|---|---|
| **0 — Foundation** | Project skeleton, Docker, settings, base models, Celery, Channels, AI interface stub, market calendar, circuit breaker skeleton, logging | Running Docker stack, all apps registered, CI passing |
| **1 — Market Data** | Ingestion, TimescaleDB, OHLCV storage, data provider interface, REST API | Tick data flowing for NIFTY 50 symbols |
| | *Batch 1.2b — Zerodha Live Adapter:* Encrypted storage for user-supplied broker credentials (Fernet-based field, key sourced from environment, never hardcoded) | Broker credentials persisted securely |
| **2 — Technical Analysis** | Indicator computation triggered by ingestion, TimescaleDB indicator tables, API | Indicators computed and queryable |
| **3 — Intelligence Engine** | IntelligencePacket assembly, data quality scoring, freshness validation | IntelligencePacket built per symbol after each tick |
| **4 — Rule Engine** | First 10 rules, freshness guard, rule registry, RuleExecution log | Rules firing AnalysisEvents on test data |
| **5 — AI + Recommendations + Trader Memory** | Gemini + DeepSeek wired, prompt templates (DB-versioned), Model Router, Strategy Registry, Confidence Engine V2, recommendation lifecycle, explanation composition | End-to-end: rule fires → AI reasons → recommendation stored with explanation |
| **6 — Notifications + WebSocket** | Django Channels, WebSocket consumers, notification delivery, user preferences | Recommendations pushed to frontend in real-time |
| **7 — News + Announcements + Global Markets** | NLP, filing feeds, global indices, FII data, IntelligencePacket enriched | Full context packet reaching AI |
| **8 — Frontend Dashboard** | React app, all pages, TradingView charts, WebSocket integration | Usable web interface end-to-end |
| **9 — Portfolio + Options Chain** | Position tracking, P&L, options analysis, options context in AI prompts | Portfolio page, options-aware recommendations |
| **10 — Pattern Engine** | Historical similarity scoring, feature vector precomputation, pattern context in AI prompts | "Today resembles…" context delivered to AI |
| **11 — Backtesting + Calibration** | Outcome tracking, accuracy reports, confidence calibration, drift detection | Trader Memory outcomes populated nightly |
| **12 — Hardening** | Load testing, security review, SEBI disclaimer integration, disaster recovery drill, staging environment | Production-ready system |

---

## 22. Architecture Decision Records

| ADR | Decision | Rationale |
|---|---|---|
| ADR-001 | Layered monolith first | Operational simplicity, faster iteration, identical internal boundaries enable future extraction |
| ADR-002 | Rule engine before AI | LLM calls are expensive and rate-limited; monitoring must work during AI outages |
| ADR-003 | Abstract AI provider interface | Gemini today, Claude/OpenAI/Ollama later — should be a config change, not a code change |
| ADR-004 | TimescaleDB for time-series | Single Postgres engine, no second DB system, battle-tested for financial time-series |
| ADR-005 | Market Intelligence Engine | Clean separation between data assembly and rule evaluation; AI always receives one consistent packet |
| ADR-006 | Trader Memory | Enables calibration, RAG, prompt improvement, and regulatory auditability from day one |
| ADR-007 | Pattern Engine in Phase 10 | Requires historical data volume to be meaningful; correct to defer, not skip |
| ADR-008 | Named Celery queues | AI tasks, data tasks, and notification tasks have different scaling profiles; shared queue creates head-of-line blocking |
| ADR-009 | pgbouncer for connection pooling | Celery workers under load exhaust Postgres max_connections without pooling |
| ADR-010 | Soft delete for financial records | Auditability requires "what did this user have configured when this recommendation was made" |
| ADR-011 | API versioning from Phase 1 | Retrofitting `/api/v1/` after clients exist breaks compatibility |
| ADR-012 | Abstract market data provider | Same interface pattern as AI providers — swapping data vendors should be a config change |
| ADR-013 | Event bus transport: Redis Streams (not Pub/Sub) | At-least-once delivery for AnalysisEvent; Pub/Sub retained for notifications fan-out (see ADR-013 doc for full trade-off table) |
| ADR-014 | Intelligence Packet V2 — Portfolio, Risk, and Regime Context Blocks | **DEFERRED to Phase 9.** Two-event enrichment pipeline: ``IntelligenceService.build_packet()`` publishes ``INTELLIGENCE_PACKET_READY``; ``PortfolioRiskContextBuilder`` reads ``PositionSnapshot``/``RiskStateSnapshot`` from EventBus streams, attaches them, and republishes as ``INTELLIGENCE_PACKET_ENRICHED``. The code (``PortfolioRiskContextBuilder``, ``IntelligenceService.build_packet()``) remains in the tree but is not wired into any automatic subscriber until Phase 9. |
| ADR-015 | DeepSeek AI Provider | Adds DeepSeek as a first-class AI provider via OpenAI-compatible chat API; Phase 0 covers auth/health, Phase 4 adds inference |
| ADR-016 | Prompt Manager and Signal Schema | Structured Jinja2 prompt templates with versioning; PromptManager service; IntelligenceResponseSchema for AI output validation |
| ADR-017 | Strategy Registry | Deterministic event-to-strategy matching via TradingStrategy model with symbol/sector filters, per-strategy preferred_provider hook into ModelRouter, and configurable confidence/risk thresholds |
| ADR-018 | Intelligence Domain Architecture | Clean Architecture layering for AI reasoning; IntelligenceSignal enum (BUY/SELL/WAIT/EXIT/REDUCE); domain boundaries between Trading Core and Intelligence domain |
| ADR-019 | Model Router | Deterministic AI provider selection via 9-step routing policy; reuses CircuitBreakerFactory, no dependency on complete() |
| ADR-020 | Model Router — Provider-Preference Enhancement | preferred_provider hint inserted before capability/health batch filters; decision_trace for observability; config hot-reload for cost/latency tiers |
| ADR-021 | Persisted Prompt Versioning & Rollback | DB-backed PromptVersion model; activate_version/rollback/get_history governance; kill-switch guarded |
| ADR-022 | Strategy Registry (implementation) | Supersedes doc-only ADR-017 with TradingStrategy model, StrategyMatcher, event-driven matching pipeline |
| ADR-023 | Confidence Engine V2 | Deterministic confidence adjustment from raw LLM output; data-quality penalties, strategy threshold checks, audit trail |
| ADR-024 | Recommendation Explanation Boundary | ExplanationComposer consumes validated LLM trade_explanation/risk_explanation; appends confidence adjustment and strategy context |
| ADR-025 | AI/Intelligence App Registration & Migrations | apps.ai_engine, apps.intelligence, apps.recommendations, apps.strategy_registry registered in INSTALLED_APPS with initial migrations |
| ADR-026 | Market Context Engine (Batch AI-4) | Extends existing MarketContextService with deterministic scoring (bullishness, bearishness, volatility, trend, liquidity, momentum, overall_context_confidence); completes SignalContext → AI prompt wiring via MarketContextCache; PatternContext consumption dormant pending Pattern Engine |
| ADR-027 | Deterministic Risk Management (Batch M3) | New `apps.risk_management` context consumes `rule_engine.RuleFired` → `RiskApproved`/`RiskRejected`; stub capital gateway (`portfolio_gateway_impl="stub"`, never backs a real order); additive `entry_price` in M2 trigger_data; Postgres-backed fail-closed kill switch (GLOBAL→ACCOUNT→SYMBOL) with short-TTL cache |
| ADR-028 | Portfolio & Capital Management (Batch M4) | New `apps.portfolio` context: authoritative `AccountCapitalState` ledger + ledger-style `Position` lifecycle + idempotent `PositionFillExecution`; 5 approved events (`positions.*` feed unmodified dashboard projections, rich `PositionClosed` feeds `TradeProjectionService`; `portfolio.*` new territory); risk gateways swapped to real `RealCapitalGateway`/`RealPortfolioStateGateway` (`implementation_name="portfolio_v1"`, default `RISK_MANAGEMENT_GATEWAY_IMPL="portfolio"`, stub as defensive fallback); Portfolio API at `/api/v1/portfolio/`; 8-dp quantize at persistence boundaries + natural-form Decimal payloads; scope-wrapper permission classes fix in portfolio + risk_management |

---

*Architecture v1.0 — Frozen. No changes without explicit approval.*
*All future development sessions reference this document as the permanent design authority.*
