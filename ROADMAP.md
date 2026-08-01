# TradeVision AI — Development Roadmap

> Last updated: 2026-08-01

---

## Phase Status

| Phase | Focus | Status | Tests |
|---|---|---|---|
| **0 — Foundation** | Project skeleton, Docker, settings, base models, Celery, Channels, AI interface stub, market calendar, circuit breaker skeleton, logging | **COMPLETE** | 206 passing |
| **1 — Market Data** | Ingestion, TimescaleDB, OHLCV storage, data provider interface, REST API | NOT STARTED | — |
| **2 — Technical Analysis** | Indicator computation triggered by ingestion, TimescaleDB indicator tables, API | NOT STARTED | — |
| **3 — Intelligence Engine** | IntelligencePacket assembly, data quality scoring, freshness validation | **PARTIAL** (B.0 registered, PineOutput model migrated) | — |
| **4 — Rule Engine** | First 10 rules, freshness guard, rule registry, RuleExecution log | NOT STARTED | — |
| **5 — AI + Recommendations + Trader Memory** | Gemini + DeepSeek wired, prompt templates (DB-versioned), Model Router, Strategy Registry, Confidence Engine V2, recommendation lifecycle, explanation composition | **PARTIAL** (Batch A+B + AI-5B + AI-5C delivered; AI-5C wired circuit-breaker record_success/record_failure into the orchestrator provider loop) | 87 passing (AI-5B/AI-5C batch targets) |
| **6 — Notifications + WebSocket** | Django Channels, WebSocket consumers, notification delivery, user preferences | NOT STARTED | — |
| **7 — News + Announcements + Global Markets** | NLP, filing feeds, global indices, FII data, IntelligencePacket enriched | NOT STARTED | — |
| **8 — Frontend Dashboard** | React app, all pages, TradingView charts, WebSocket integration | NOT STARTED | — |
| **9 — Portfolio + Options Chain** | Position tracking, P&L, options analysis, options context in AI prompts | NOT STARTED | — |
| **10 — Pattern Engine** | Historical similarity scoring, feature vector precomputation, pattern context in AI prompts | **COMPLETE** (Batch AI-5) | 48 passing (DB-backed) |
| **11 — Backtesting + Calibration** | Outcome tracking, accuracy reports, confidence calibration, drift detection | NOT STARTED | — |
| **12 — Hardening** | Load testing, security review, SEBI disclaimer integration, disaster recovery drill, staging environment | NOT STARTED | — |

---

## Phase 5 — AI + Recommendations + Trader Memory

### Batch AI-5C — Live DeepSeek Reachability + Circuit-Breaker Feedback Loop (delivered)

- **Circuit-breaker feedback loop** wired into `AIReasoningOrchestrator._call_ai`: each provider attempt now calls `breaker.record_success()` on success and `breaker.record_failure()` on each caught exception, using the same `get_or_create(f"ai-provider-{provider_name}")` breaker ModelRouter already reads for routing exclusions. Additive instrumentation — no change to `ModelRouter`, the DeepSeek provider, or `AIResponseSchema`. After N consecutive failures the router excludes the provider (OPEN); HALF_OPEN stays eligible (ADR-019 health filter).
- **End-to-end reachability trace** test: RuleFired → orchestrator → DeepSeek `complete()` (mocked httpx) → `AIResponseValidator` → `RecommendationIssued` → `create_recommendation` → persisted `Recommendation` row with `provider="deepseek"` + original `correlation_id`.
- **Key provisioning**: `backend/.env` (read by python-decouple from the process CWD) contains `GEMINI_API_KEY=test-key` — a **placeholder, not a usable credential**. `DEEPSEEK_API_KEY` is unset. A live DeepSeek call requires a real key; CI uses recorded/mocked `httpx` fixtures, not real keys.
- **Batch targets**: 87 passing (AI-5B 11 + AI-5C 7 + DeepSeek provider 22 + circuit breaker 10 + router/orchestrator suites).

---

## Phase 0 — Foundation (COMPLETE)

### Deliverables

- **Docker stack**: PostgreSQL (TimescaleDB), Redis, Celery workers (market, AI, default), Backend (Daphne/ASGI)
- **Django settings**: base.py, development.py, production.py, testing.py
- **Custom User model**: UUID pk, email-only auth, roles (ADMIN, TRADER, READ_ONLY)
- **JWT endpoints**: token obtain, token refresh, user profile
- **Health checks**: liveness, db, cache, celery, system
- **BaseModel**: UUID + timestamps + soft-delete
- **Management commands**: wait_for_db, wait_for_redis, system_check, seed_admin
- **AI provider interface**: BaseAIProvider ABC, GeminiProvider, OpenAI/Claude/Ollama stubs
- **Market data provider interface**: BaseMarketDataProvider ABC, MockMarketDataProvider
- **Rule engine registry**: thread-safe RuleRegistry
- **Circuit breaker**: Redis-backed with CLOSED/OPEN/HALF_OPEN states
- **Market calendar**: NSE trading hours, holidays, session states
- **Structured logging**: structlog + JSON (prod) / Console (dev)
- **Prometheus metrics**: 15+ metric definitions
- **Middleware**: CorrelationIDMiddleware, RequestLoggingMiddleware
- **Config wrapper**: TradeVisionConfig with typed property accessors
- **Repository ABC**: generic BaseRepository[T]
- **BaseService + BaseTask**: structured logging, correlation ID binding, retry constants
- **Protocols**: Identifiable, Timestamped, SoftDeletable, Auditable
- **Test suite**: 17 test files, 206 tests passing

### Verification

- All 23 source files present and syntactically clean
- All 17 test files present
- No circular imports (core/ → apps/, providers → factory)
- Middleware order: CorrelationID before RequestLogging
- MARKET_DATA_PROVIDER configured in settings

---

## Phase 1 — Market Data (Next)

### Deliverables

- TimescaleDB hypertables for OHLCV + tick storage
- OHLCV models with TimescaleDB-compressed hypertables
- Market data repository (upsert/idempotent insert)
- Market data services (fetch_and_store, freshness validation)
- Celery tasks (periodic OHLCV polling, tick ingestion)
- REST API (DRF views + serializers for OHLCV query)
- WebSocket consumer (real-time tick push)
- Admin registration
- Comprehensive test suite

---

*Architecture v1.0 — Frozen. No changes without explicit approval.*
