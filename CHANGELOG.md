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

*Architecture v1.0 — Frozen.*
