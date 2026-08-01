"""
Batch AI-5C — Circuit-breaker feedback loop integration tests.

Proves the orchestrator's provider-call loop records success/failure on the
same ``ai-provider-{name}`` circuit ModelRouter already reads, so that after
N consecutive failures the router excludes the provider (OPEN), while a
HALF_OPEN provider remains eligible — per ADR-019 health filter.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from core.ai.base_provider import AIRawResponse
from core.ai.exceptions import AIConnectionError
from core.resilience.circuit_breaker import (
    CircuitBreakerFactory,
    CircuitState,
)


def _mock_redis() -> MagicMock:
    """Return a mock Redis client that behaves like an in-memory store."""
    store: dict[str, str | int] = {}

    def _set(key, value, **kwargs):
        nx = kwargs.get("nx", False)
        if nx and key in store:
            return False
        store[key] = value
        return True

    def _delete(key):
        store.pop(key, None)
        return 1

    mock = MagicMock()
    mock.exists = MagicMock(side_effect=lambda k: k in store)
    mock.get = MagicMock(side_effect=lambda k: store.get(k))
    mock.incr = MagicMock(side_effect=lambda k: store.update({k: store.get(k, 0) + 1}) or store[k])
    mock.set = MagicMock(side_effect=_set)
    mock.delete = MagicMock(side_effect=_delete)

    pipe_mock = MagicMock()
    pipe_mock.set = MagicMock(side_effect=_set)
    pipe_mock.delete = MagicMock(side_effect=_delete)
    pipe_mock.execute = MagicMock(return_value=[True, 1])
    mock.pipeline = MagicMock(return_value=pipe_mock)
    return mock


def _build_orchestrator_with_factory(factory: CircuitBreakerFactory):
    from apps.ai_engine.infrastructure.ai_reasoning_orchestrator import (
        AIReasoningOrchestrator,
    )

    with patch(
        "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.CircuitBreakerFactory",
        return_value=factory,
    ):
        orchestrator = AIReasoningOrchestrator()
    return orchestrator


def _mock_router(decision: MagicMock):
    from apps.ai_engine.model_router import ModelRouter

    router = MagicMock(spec=ModelRouter)
    router.route.return_value = decision
    return router


def _patch_router_priority(only: list[str]):
    return patch(
        "apps.ai_engine.model_router.config",
        ai_provider_priority=only, ai_provider_disabled=set(), ai_cost_tier_ceilings={}, ai_routing_fast_tier_threshold_ms=1500,
    )


def _raw_response(provider: str) -> AIRawResponse:
    from datetime import datetime, timezone
    from decimal import Decimal

    return AIRawResponse(
        request_id=uuid.uuid4(),
        provider=provider,
        raw_text='{"direction": "BUY", "confidence_score": 0.85, '
        '"reasoning": "Strong technical setup with sufficient length", '
        '"risk_level": "LOW", "risk_explanation": "Risk explanation with sufficient length", '
        '"key_factors": ["factor1"], "contradicting_factors": [], '
        '"time_horizon": "SHORT", "follow_up_triggers": []}',
        input_tokens=100,
        output_tokens=50,
        latency_ms=500.0,
        estimated_cost_usd=Decimal("0.001"),
        timestamp=datetime.now(timezone.utc),
    )


class TestAICircuitBreakerFeedback:
    """Orchestrator provider loop records breaker success/failure."""

    def test_success_records_breaker_success(self) -> None:
        factory = CircuitBreakerFactory(_mock_redis())
        breaker = factory.get_or_create("ai-provider-deepseek")
        orchestrator = _build_orchestrator_with_factory(factory)

        mock_provider = MagicMock()
        mock_provider.complete.return_value = _raw_response("deepseek")

        decision = MagicMock()
        decision.selected_provider.value = "deepseek"
        decision.fallback_chain = ()

        with (
            patch(
                "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider",
                return_value=mock_provider,
            ),
        ):
            orchestrator._model_router = _mock_router(decision)

            result = orchestrator._call_ai("test prompt", "RELIANCE", uuid.uuid4())

        assert result is not None
        assert result.provider == "deepseek"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_provider_error_records_breaker_failure(self) -> None:
        factory = CircuitBreakerFactory(_mock_redis())
        breaker = factory.get_or_create("ai-provider-deepseek")
        orchestrator = _build_orchestrator_with_factory(factory)

        mock_provider = MagicMock()
        mock_provider.complete.side_effect = AIConnectionError("Simulated outage")

        decision = MagicMock()
        decision.selected_provider.value = "deepseek"
        decision.fallback_chain = ()

        with (
            patch(
                "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider",
                return_value=mock_provider,
            ),
        ):
            orchestrator._model_router = _mock_router(decision)

            result = orchestrator._call_ai("test prompt", "RELIANCE", uuid.uuid4())

        assert result is not None
        assert result.provider == "fallback"
        assert breaker.failure_count == 1

    def test_unexpected_error_records_breaker_failure(self) -> None:
        factory = CircuitBreakerFactory(_mock_redis())
        breaker = factory.get_or_create("ai-provider-deepseek")
        orchestrator = _build_orchestrator_with_factory(factory)

        mock_provider = MagicMock()
        mock_provider.complete.side_effect = ValueError("Unexpected failure")

        decision = MagicMock()
        decision.selected_provider.value = "deepseek"
        decision.fallback_chain = ()

        with (
            patch(
                "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider",
                return_value=mock_provider,
            ),
        ):
            orchestrator._model_router = _mock_router(decision)

            result = orchestrator._call_ai("test prompt", "RELIANCE", uuid.uuid4())

        assert result is not None
        assert result.provider == "fallback"
        assert breaker.failure_count == 1

    def test_fallback_chain_records_failure_then_success_per_provider(self) -> None:
        factory = CircuitBreakerFactory(_mock_redis())
        gemini_breaker = factory.get_or_create("ai-provider-gemini")
        deepseek_breaker = factory.get_or_create("ai-provider-deepseek")
        orchestrator = _build_orchestrator_with_factory(factory)

        mock_gemini = MagicMock()
        mock_gemini.complete.side_effect = AIConnectionError("Gemini down")
        mock_deepseek = MagicMock()
        mock_deepseek.complete.return_value = _raw_response("deepseek")

        def provider_side_effect(name: str):
            if name == "gemini":
                return mock_gemini
            return mock_deepseek

        decision = MagicMock()
        decision.selected_provider.value = "gemini"
        decision.fallback_chain = (__import__("core.constants", fromlist=["AIProviderName"]).AIProviderName.DEEPSEEK,)

        with (
            patch(
                "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider",
                side_effect=provider_side_effect,
            ),
        ):
            orchestrator._model_router = _mock_router(decision)

            result = orchestrator._call_ai("test prompt", "RELIANCE", uuid.uuid4())

        assert result is not None
        assert result.provider == "deepseek"
        assert gemini_breaker.failure_count == 1
        assert deepseek_breaker.failure_count == 0
        assert deepseek_breaker.state == CircuitState.CLOSED


class TestAICircuitBreakerRouting:
    """Real breaker + real router: OPEN excludes, HALF_OPEN stays eligible."""

    def test_router_excludes_provider_after_threshold_failures(self) -> None:
        from apps.ai_engine.model_router import ModelRouter

        factory = CircuitBreakerFactory(_mock_redis())
        breaker = factory.get_or_create(
            "ai-provider-deepseek", failure_threshold=2, recovery_timeout=60
        )
        orchestrator = _build_orchestrator_with_factory(factory)
        router = ModelRouter(factory)
        orchestrator._model_router = router

        mock_provider = MagicMock()
        mock_provider.complete.side_effect = AIConnectionError("Outage")

        decision = MagicMock()
        decision.selected_provider.value = "deepseek"
        decision.fallback_chain = ()

        with (
            _patch_router_priority(["deepseek", "gemini"]),
            patch(
                "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider",
                return_value=mock_provider,
            ),
            patch(
                "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter",
                return_value=router,
            ),
        ):
            for _ in range(2):
                orchestrator._call_ai("test prompt", "RELIANCE", uuid.uuid4())

            assert breaker.state == CircuitState.OPEN

            decision_after = router.route(
                __import__(
                    "apps.ai_engine.model_router",
                    fromlist=["RoutingRequest"],
                ).RoutingRequest(
                    event_type=__import__(
                        "core.events.event_types",
                        fromlist=["EventType"],
                    ).EventType.PRICE_MOVEMENT,
                    context_tokens_estimate=500,
                )
            )
            assert decision_after.routing_metadata.excluded.get("deepseek") == "circuit breaker is OPEN"
            assert decision_after.selected_provider.value == "gemini"

    def test_half_open_provider_remains_eligible(self) -> None:
        from apps.ai_engine.model_router import ModelRouter, RoutingRequest
        from core.events.event_types import EventType

        factory = CircuitBreakerFactory(_mock_redis())
        breaker = factory.get_or_create(
            "ai-provider-deepseek", failure_threshold=2, recovery_timeout=60
        )
        breaker.record_failure()
        breaker.record_failure()
        breaker._redis.delete(breaker._open_key)
        assert breaker.state == CircuitState.HALF_OPEN

        router = ModelRouter(factory)

        with _patch_router_priority(["deepseek"]):
            decision = router.route(
                RoutingRequest(
                    event_type=EventType.PRICE_MOVEMENT,
                    context_tokens_estimate=500,
                )
            )

        assert decision.selected_provider.value == "deepseek"
        assert "deepseek" not in decision.routing_metadata.excluded
