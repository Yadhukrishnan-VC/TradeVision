# Changelog

All notable changes to TradeVision AI will be documented in this file.

---

## [0.1.0] — 2026-07-12

### Phase 0 — Foundation (Complete)

**Added:**
- Docker stack with PostgreSQL (TimescaleDB), Redis, Celery workers, Backend (Daphne/ASGI)
- Django settings (base, development, production, testing)
- Custom User model with UUID pk, email auth, and roles
- JWT authentication endpoints (token obtain, refresh, profile)
- Health check endpoints (liveness, db, cache, celery, system)
- BaseModel with UUID, timestamps, and soft-delete
- Management commands (wait_for_db, wait_for_redis, system_check, seed_admin)
- AI provider interface (BaseAIProvider ABC) with GeminiProvider and 3 stubs
- Market data provider interface (BaseMarketDataProvider ABC) with MockMarketDataProvider
- Rule engine registry (thread-safe RuleRegistry)
- Circuit breaker (Redis-backed, CLOSED/OPEN/HALF_OPEN)
- Market calendar (NSE trading hours, holidays, session states)
- Structured logging (structlog + JSON)
- Prometheus metrics definitions (15+ metrics)
- CorrelationIDMiddleware and RequestLoggingMiddleware
- TradeVisionConfig centralised config wrapper
- Generic BaseRepository[T] ABC
- BaseService with structured logging and correlation ID binding
- BaseTask with retry constants and idempotency key generation
- Structural protocols (Identifiable, Timestamped, SoftDeletable, Auditable)
- Core test suite (17 test files, 206 tests passing)

---

## [Unreleased]

### Fixed
- Registered apps.common, apps.accounts, apps.health in INSTALLED_APPS (Issue 1)
- Activated custom User model via AUTH_USER_MODEL (Issue 2)
- Generated and verified initial database migrations for accounts (Issue 3)
- Wired apps.accounts and apps.health URLconfs into the root router; removed placeholder inline health check (Issue 4)

### Changed
- Corrected PROJECT_STATE.md: removed false "Encryption utilities" completion claim from Phase 0; scheduled the real requirement under Batch 1.2b (Issue 5)
- Centralized Redis client construction behind a connection-pooled factory (core/redis_client.py); EventBus now uses it (Issue 8)
- Migrated AnalysisEvent transport from Redis Pub/Sub to Redis Streams with consumer groups, per ADR-013, for reliable at-least-once delivery. Notifications/WebSocket fan-out remains on Pub/Sub, unchanged. (Issue 6)
- Added single-probe locking to CircuitBreaker's HALF_OPEN state to prevent concurrent trial calls across workers (Issue 7)

### Added
- docs/adr/ADR-013-event-bus-streams.md

---

## [0.2.0] — 2026-07-27

### Batch B — AI/Intelligence Domain Enhancement

**Added:**
- B.0: Registered all AI/Intelligence apps (ai_engine, intelligence, recommendations, strategy_registry) in INSTALLED_APPS
- B.0: Initial migrations for all 4 apps (PromptVersion, ConfidenceEvaluation, PineOutput, RecommendationExplanation, TradingStrategy)
- B.1: Model Router enhancements — decision_trace on RoutingDecision, preferred_provider evaluated before capability/health batch filters, get_provider_capabilities() for config hot-reload
- B.2: Prompt Manager DB-backed persistence — PromptVersion model, activate_version/rollback/get_history methods, kill-switch guarded
- B.3: Strategy Registry (new app) — TradingStrategy model with symbol/sector filters, preferred_provider hints, confidence/risk thresholds; StrategyMatcher.match(); match_packet Celery task
- B.4: Confidence Engine V2 — ConfidenceEvaluation model, ConfidenceEngine.evaluate() with data-quality penalties and strategy threshold checks, evaluate_and_persist() for audit trail
- B.5: Recommendation Explanation — RecommendationExplanation model, ExplanationComposer.compose()/compose_fallback(), compose_explanation Celery task
- Kill-switch settings (all default False): STRATEGY_REGISTRY_ENABLED, PROMPT_VERSIONING_PERSISTENCE_ENABLED, CONFIDENCE_ENGINE_V2_ENABLED, MODEL_ROUTER_PREFERRED_PROVIDER_ENABLED
- Celery task routes for all new tasks on ai_reasoning queue
- TaskName enum entries for MATCH_STRATEGY, EVALUATE_CONFIDENCE, COMPOSE_EXPLANATION
- Draft ADRs: ADR-020 through ADR-025

**Changed:**
- Expanded development status in PROJECT_STATE.md to reflect partial Phase 3 and Phase 5 completion
- core/config.py: added 4 new kill-switch config properties

---
