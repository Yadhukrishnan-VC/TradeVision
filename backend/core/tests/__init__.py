"""
TradeVision AI — Core layer test suite.

Tests in this package cover the framework and infrastructure modules in
``core/``. All external dependencies (Redis, AI provider SDKs, Django ORM)
are mocked so these tests run without any running services.

Test modules:
    test_constants             — Enum completeness and value uniqueness
    test_ai_exceptions         — AI exception hierarchy and inheritance
    test_ai_provider_contract  — Provider interface compliance and lifecycle
    test_provider_factory      — AI singleton, reset, unknown provider
    test_rule_registry         — register, unregister, evaluate_all
    test_base_task             — Correlation ID, timing, retry constants
    test_market_calendar       — Session boundaries, holidays, next_trading_day
    test_circuit_breaker       — State transitions (mocked Redis)
    test_event_types           — Frozen dataclasses, timezone validation
    test_responses             — to_dict() shape for all response types
    test_repository            — Abstract interface enforcement
    test_services              — BaseService logger and context helpers
    test_middleware            — Correlation ID header passthrough
    test_config                — Typed attribute access and defaults
    test_market_data_providers — MockProvider contract and factory lifecycle
"""
