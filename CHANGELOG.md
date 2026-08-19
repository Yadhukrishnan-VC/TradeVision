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

### Batch 2 — Research Integrity Suite (2026-08-19)

**Added:**
- Adversarial test suite `backend/tests/research_integrity/` (17 tests, self-contained conftest, real event-chain replay: TA ingestion → event bus → intelligence → rule_engine → risk_management → execution → paper broker) covering the seven research-integrity attacks: same-candle execution, look-ahead bias, future-data leakage, IS/OOS contamination, walk-forward contamination, timestamp leakage, survivorship bias
- Deterministic adversarial datasets: bars with missing `open`, bars outside/on the inclusive range boundaries, duplicate bar timestamps, per-window contaminating trades, wall-clock-vs-simulated-time splits
- `docs/RESEARCH_INTEGRITY.md` — attacks attempted, findings, fixes, remaining risks
- `tests/` added to pytest `testpaths` so the suite runs with the default suite

**Fixed:**
- RESEARCH-INTEGRITY-1 (IS/OOS contamination): `BacktestStatsService.run_stats` partitioned on wall-clock `order.created_at` (replay run in the present) vs historical `split_ts`, so every real-replay trade landed in OOS and IS was always empty. Now partitions on the first fill's simulated `occurred_at` (`first_fill_at` map); boundary inclusive (`<= split_ts` → IS). Regression-pinned by `test_is_oos_contamination.py`.
- RESEARCH-INTEGRITY-2 (look-ahead fill): `bar_open = raw.get("open") or raw.get("close")` filled deferred orders at a bar's close when `open` was missing — a price not yet known at the open. Now requires a real `open` and fails safe (order stays pending; later bar or final flush fills it). Regression-pinned by `test_lookahead_bias.py`.

**Changed:**
- `backend/pytest.ini`: `testpaths` now includes `tests/`

**Remaining risks (documented):** final-bar close flush (end-of-sample liquidation convention), `price_source` wall-clock/sim-time `ValueError` (logged+swallowed), hardcoded 1M exposure cap, `order.created_at` stays wall-clock audit-only


### Live/Paper Trading Readiness (2026-08-19)

**Added:**
- `requirements/base.txt` now declares the seven runtime deps restored by the remediation batch (exact pins: `django-prometheus==2.4.0`, `python-decouple==3.8`, `structlog==24.4.0`, `channels==4.3.2`, `channels-redis==4.3.0`, `Jinja2==3.1.6`, `requests==2.34.2`) with constraint comments — a fresh rebuild from requirements only now yields a working venv (`pip check` clean, `manage.py check` passes, zero manual installs). Fresh-rebuild transitive resolution moved celery/django-celery-*/Faker/django-stubs to newer allowed versions; full suite unchanged
- `manage.py backfill_historical` — operator CLI wrapping `HistoricalSyncService.backfill` unchanged: `--provider/--symbols/--tokens/--timeframe/--from/--to/--days/--dry-run`; dry-run fetches and reports counts without persisting, real run persists via the service; per-instrument failure isolation + summary + exit 1 on any failure. Verified dry-run (2×2 bars, nothing persisted) and real run (10 candles persisted) against the sandbox DB with the `paper` provider
- Startup system check `config.E001`/`config.E002` (registered via `apps/common/apps.py` `ready()`): fails loud when a live settings module (`prod`/`staging`) points at a DB whose name carries a `test` marker, or a dev settings module points at a DB with no `test`/`dev` marker; word-boundary marker matching (`dev` ≠ substring of `tradevision`); pytest harness settings exempt. Verified both directions fire and compliant pairs pass
- `manage.py rule_gate_report` — per-rule × per-regime ADR-029 §4 gate visibility (`GO`/`NO_GO`/`INSUFFICIENT_DATA`/`NOT_VALIDATED`/`DISABLED`/`NO_CONFIG`), mirroring `_filter_by_gate` reasons; `--regime` filter, `--verbose` payloads; all verdict classes demonstrated against seeded configs
- Regression tests (16): `config/tests/test_env_db_separation_check.py` (both directions + pass cases + substring guard + harness exemption), `apps/market_data/tests/unit/test_backfill_historical_command.py` (dry-run persists nothing, real run persists, unknown-symbol failure, `--from`/`--days` exclusivity), `apps/rule_engine/tests/unit/test_rule_gate_report_command.py` (all verdict rows + fireable counts)
- `docs/LIVE_READINESS_BLOCKERS.md` — before/after per task, rebuild proof, dry-run/real-run and check outputs, gate report output, consequences

**Changed:**
- Dev DB convention: `manage.py` runs now require a DB name carrying a `test`/`dev` token (e.g. `POSTGRES_DB=tradevision_test`; already the value in `backend/.env`). `infra/docker-compose.yml` default `POSTGRES_DB=tradevision_db` now trips `config.E002` under dev settings — compose operators must use a `*_dev*`/`*_test*` name (documented, not fixed)

**Findings:** CI check unaffected (harness settings exempt); no schema changes (`makemigrations --check` clean); pre-existing 34 failed / 15 errors unchanged


### Remediation Batch — Environment & Runtime (2026-08-19)

**Fixed:**
- ENV-1 (Django version drift): rebuilt `backend/.venv` from `requirements/dev.txt` → Django 5.0.14 (was 6.0.7 vs pin `django>=5.0,<5.1`); restored undeclared runtime deps (`python-decouple`, `structlog`, `channels`, `channels-redis`, `django-prometheus==2.4.0`, `Jinja2`, `requests`) at old-venv-compatible versions; `pip check` clean
- ENV-2 (migration drift): generated + applied 4 non-destructive migrations for `recommendations`, `rule_engine`, `signals_engine`, `trader_memory` — root cause was `help_text` drift on BaseModel fields (no-op `AlterField`s) and `Meta.indexes` without explicit `name=` (4 `ALTER INDEX … RENAME`); `makemigrations --check --dry-run` now exits 0
- ENV-3 (prompt templates silently failing): `PromptManager._load_templates` logged `extra={"filename": …}` — a reserved `LogRecord` attribute — so `logger.info` raised on every iteration, was swallowed by the broad `except`, and reported `prompt_template_load_failed` for all 11 event types while persistence never ran. Renamed key to `template_filename`. Codebase-wide audit for the same mistake found+fixed two more live instances: `instrument_sync_complete` `extra={"created"}` → `created_count` (crashed end-of-sync log), DRF exception handler `extra={"message"}` → `error_message` (crashed on every API error response)

**Added:**
- `apps/ai_engine/tests/test_prompt_manager_regression.py` (3 tests: all 11 templates load, no load-failure when INFO enabled, all 11 versions persist) — verified to fail against the old bug
- `docs/REMEDIATION_BATCH_ENV_RUNTIME.md` — root causes, migration rationale, before/after logs, raw verification output, findings

**Findings (documented, not fixed):** runtime deps undeclared in requirements files (notably `requests`, imported by 4 provider modules); `django-prometheus>=2.5` excludes Django 5.0.x; `recommendations` migration `0004` filename/content mismatch (Django-6-generated, dropped renames); stray `opencv-python-headless` in old venv; `psql` not installed; 34 pre-existing failed / 15 pre-existing errors unchanged


### Batch M4 — Portfolio & Capital Management (2026-08-03)

**Added:**
- `apps.portfolio` bounded context (ADR-028): authoritative `AccountCapitalState` per-account capital ledger, ledger-style `Position` lifecycle (open → quantity-changed\* → closed, with over-offset flip), idempotent `PositionFillExecution` (`source_fill_id` unique guard mirroring `RuleExecution`/`RiskDecisionExecution`)
- `CapitalService` — deposit / withdraw / reserve_margin / release_margin / record_realized_pnl / reconcile_unrealized; `equity = cash + unrealized_pnl_today`, `available_capital = cash - margin_used`; insufficient-available-capital rejection; `Account` created ⇒ zero-balance `AccountCapitalState` via additive `post_save` signal (apps.accounts untouched)
- `PositionLedgerService` — `record_fill` / `close_position` / `adjust_quantity`, all idempotent on `source_fill_id`, one DB transaction per applied fill (position + margin + realized P&L + events)
- 5 approved events: `positions.PositionOpened` / `PositionQuantityChanged` / **rich** `PositionClosed` (symbol, side, entry/exit price, quantity, realized_pnl, realized_pnl_pct, holding_period_seconds, opened_at — the locked `TradeProjectionService` contract) + `portfolio.AccountCapitalChanged` / `portfolio.ExposureChanged`
- `RealCapitalGateway` / `RealPortfolioStateGateway` (`implementation_name="portfolio_v1"`) implementing the M3 risk ports; `apps.risk_management.gateways.factory` selects impl from `RISK_MANAGEMENT_GATEWAY_IMPL` **defaulting to `"portfolio"`** (stub remains only as a defensive fallback); Celery task `evaluate_rule_firing` now uses the factory
- Portfolio API at `/api/v1/portfolio/`: summary (`read:portfolio`), open positions with live marks (`read:portfolio`), manual/paper fill recording (`manage:execution`; `201` applied / `200` duplicate-skipped / `400` domain error)
- 8-dp money convention: `quantize_money()` at every persistence boundary + natural-form Decimal payloads (`"200"` not `"200.00000000"`)
- 122 portfolio/risk tests: unit (capital invariants, position lifecycle, gateway conformance), integration (unmodified dashboard `PositionSnapshot` projection driven by fills; real `RiskEvaluationService` → `RiskApproved`/`MISSING_ACCOUNT_STATE`; correlation/causation), API (scope enforcement, idempotency, natural-form), risk API (permission fix proof)

**Fixed:**
- Latent `permission_classes = [HasAPIKeyScope.with_scope(...)]` bug (an *instance* in a list DRF instantiates ⇒ `TypeError` on every request) in `apps/portfolio` and `apps/risk_management` views — replaced with scope-wrapper permission classes matching the dashboard convention
- User-approved one-line `from uuid import UUID` in `apps/dashboard/projection/trading_core/position_projection_service.py` (pre-existing `NameError` — dashboard's own 4 `position_projection` tests now pass)

**Changed:**
- `config/settings/base.py`: `apps.portfolio` registered, `RISK_MANAGEMENT_GATEWAY_IMPL` setting added (default `"portfolio"`)
- `config/urls.py`: `api/v1/portfolio/` mounted
- `apps/risk_management/infrastructure/tasks.py`: gateway construction delegated to `gateways/factory.py`


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
