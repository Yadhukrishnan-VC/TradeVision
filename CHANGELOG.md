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

### Batch M3 — Deterministic Risk Management (2026-08-02)

**Added:**
- `apps.risk_management` bounded context (ADR-027): consumes `rule_engine.RuleFired` and produces `risk_management.RiskApproved` / `RiskRejected` events, never touching the AI/intelligence risk-context pipeline
- Deterministic fail-closed risk pipeline: 9 checks in fixed order (kill switch → data freshness → market session → instrument → stop direction → position sizing → exposure → daily loss → risk/reward), first rejection wins, `RejectionReason.UNKNOWN` on any unexpected error
- Decimal-only position sizing (`ROUND_FLOOR`) from capital × risk_pct over |entry − stop|
- Kill switch: GLOBAL → ACCOUNT → SYMBOL scopes, Postgres-backed `KillSwitchState` with partial-unique active rows, short-TTL read-through cache, **fail-closed** on any cache/db error; toggles published as `KillSwitchActivated`/`KillSwitchDeactivated` (audit-log `*` subscriber records them for free)
- `StubPortfolioStateGateway` — config-driven capital/exposure source; every read logs `WARNING`, every persisted `RiskDecisionExecution` records `portfolio_gateway_impl="stub"` (ADR-027 guardrail: never backs a real order)
- Idempotent `RiskDecisionExecution` persistence mirroring `RuleExecution` (`UniqueConstraint(analysis_event_id, rule_id)`, duplicate ⇒ skip)
- Celery task `tradevision.risk_management.evaluate_rule_firing` + event handler wired to `rule_engine.RuleFired` (correlation = analysis_event_id, causation = RuleFired.event_id)
- Risk Management API: `/api/v1/risk-management/` (decision list read-only, kill-switch activate/deactivate gated by `Scope.MANAGE_RISK_POLICY`)
- 32 unit + integration tests (per-RejectionReason, kill-switch-first ordering, fail-closed cache/db proof, idempotent duplicate delivery, correlation/causation propagation, audit entry for toggles)

**Changed:**
- M2 setup rules (Long Momentum, Short Sell, Volatility Breakout) now include `trigger_data["entry_price"] = str(current_price)` (additive amendment; regression-tested)
- `config/settings/base.py`: `apps.risk_management` registered, `RISK_MANAGEMENT` settings block added, task route + API URL wired


### Batch AI-1 — Real AI Reasoning Pipeline (2026-07-28)

**Changed:**
- TechnicalAnalysisCompleted now publishes real indicator values and price data instead of key names only
- IntelligencePacket builder (`_build_packet`) reads actual indicator/price values from the event payload — no more `Decimal("0")` placeholders
- PineOutput saver writes real indicator values instead of `0.0`
- `_call_ai()` now passes `ModelRouter` routing decision (`decision.selected_provider`) to `AIProviderFactory.get_provider()` — provider selection respects the router
- Fallback executes only after real provider failure (connection error, timeout, auth error, rate limit) — never during normal operation

**Added:**
- `DeepSeekProvider.complete()` — POST to `/v1/chat/completions` with retry logic (3 attempts, exponential backoff) for transient failures; raises typed `AIAuthenticationError`, `AIQuotaExceededError`, `AIConnectionError`, `AITimeoutError`, `AIRateLimitError`
- `GeminiProvider.complete()` — uses `google-generativeai` SDK with the same retry and error contract
- `AIProviderFactory.get_provider(provider_name)` — optional explicit provider name parameter for routing-aware selection
- Integration tests for `_call_ai()` proving real response returned when provider succeeds, fallback on connection error, `None` on unexpected error

### Batch 4 — End-to-end Pipeline Wiring (2026-07-28)

**Added:**
- TA completed handler (`ta_completed_handler.py`) — handles `TechnicalAnalysisCompleted`, saves PineOutput with real indicator values, builds `IntelligencePacket` with real data, publishes `intelligence.PacketEnriched` on System B event bus
- `AIReasoningOrchestrator` — orchestrates `StrategyMatcher` → `PromptManager` → `ModelRouter` → `DeepSeek`/`Gemini` → `AIResponseValidator` → `ConfidenceEngine`, publishes `ai_engine.RecommendationIssued`
- Subscriptions in `journal` and `dashboard` for recommendation pipeline events (`RuleFired`, `RecommendationIssued`, `RecommendationCreated`)

**Changed:**
- `rule_engine` event handlers — `SUBSCRIBED_EVENTS` correctly ordered (handler defined before reference), accepts `DomainEvent`
- `recommendations` handlers — repointed from `RuleFired` to `RecommendationIssued`; `create_recommendation` task receives pre-computed direction/confidence/strategy

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

### Quality
- QUALITY-1: Used autouse fixtures for override_settings in test_api.py to eliminate per-test with blocks
- QUALITY-2: Narrowed exception type from generic Exception to InvalidTechnicalAnalysisPayloadError in test_services.py

---

## [0.3.0] — 2026-07-28

### Technical Analysis — Bug fixes, Performance & Quality

**Fixed:**
- BUG-1: Removed duplicate @property definitions in core/config.py (5 duplicated properties deleted)
- BUG-2: Added missing get_redis_client() import and passed it to CircuitBreakerFactory in apps/ai_engine/tasks.py
- BUG-3: Changed duplicate `if` to `elif` in normalise() to prevent time field leaking as raw indicator; added test
- BUG-4: Moved indicator_count SerializerMethodField before Meta class; made read_only_fields an explicit list

**Changed:**
- PERF-1: Added .only() with exact field list and symbol.upper() in TASnapshotRepository.find_by_symbol() to reduce DB query overhead
- PERF-2: Cached TASnapshotRepository and EventBus at class level in TradingViewTechnicalAnalysisWebhookView to avoid per-request construction

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
