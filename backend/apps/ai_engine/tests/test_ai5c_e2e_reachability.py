"""
Batch AI-5C — End-to-end reachability trace (mocked httpx).

Drives the full chain with a *real* DeepSeekProvider whose httpx.Client is
mocked: RuleFired → orchestrator → DeepSeek complete() → AIResponseValidator
→ RecommendationIssued → create_recommendation task (eager) → Recommendation
row persisted with provider="deepseek" and the original correlation_id.

This is the thing AI-5B was ultimately in service of: a persisted, traceable
recommendation whose provider identity is preserved end to end.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

pytestmark = pytest.mark.django_db


@pytest.fixture
def rule_fired_event():
    from apps.eventbus.domain.events import DomainEvent

    correlation_id = uuid.uuid4()
    event = DomainEvent.create(
        event_type="rule_engine.RuleFired",
        payload={
            "symbol": "RELIANCE",
            "rule_id": "price_movement_rule",
            "event_type": "price_movement",
            "severity": "HIGH",
            "trigger_data": {"change_pct": "3.5", "indicators": {"rsi_14": 62.5}},
            "analysis_event_id": str(uuid.uuid4()),
        },
        correlation_id=correlation_id,
    )
    return event, correlation_id


def _mock_httpx_post(return_value: MagicMock) -> None:
    """Patch httpx.Client inside DeepSeekProvider to return the given response."""

    def _factory(base_url, headers=None, timeout=None):
        client = MagicMock()
        client.post.return_value = return_value
        return client

    patcher = patch("core.ai.providers.deepseek_provider.httpx.Client", side_effect=_factory)
    patcher.start()
    return patcher


def _valid_httpx_response() -> MagicMock:
    content = json.dumps({
        "direction": "BUY",
        "confidence_score": 0.85,
        "reasoning": "Strong technical setup with sufficient length for the schema",
        "risk_level": "LOW",
        "risk_explanation": "Risk explanation with sufficient length for the schema",
        "key_factors": ["RSI bullish", "Volume spike"],
        "contradicting_factors": [],
        "time_horizon": "SHORT",
        "follow_up_triggers": ["Price movement beyond threshold"],
    })
    return MagicMock(
        status_code=200,
        json=lambda: {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 60},
        },
    )


class TestEndToEndReachabilityTrace:
    def test_rule_fired_produces_persisted_deepseek_recommendation(
        self, rule_fired_event
    ) -> None:
        from apps.ai_engine.infrastructure.ai_reasoning_orchestrator import (
            AIReasoningOrchestrator,
        )
        from apps.ai_engine.model_router import ModelRouter
        from apps.ai_engine.tests.test_ai5c_breaker_feedback import _mock_redis
        from apps.eventbus.infrastructure.event_bus_factory import (
            get_event_bus,
            reset_event_bus,
        )
        from apps.recommendations.infrastructure.event_handlers import (
            register_handlers as register_recommendation_handlers,
        )
        from apps.recommendations.infrastructure.models import Recommendation
        from core.resilience.circuit_breaker import CircuitBreakerFactory

        event, correlation_id = rule_fired_event

        # DeepSeek provider with a mocked httpx client returning a valid schema
        http_patcher = _mock_httpx_post(_valid_httpx_response())
        try:
            from core.ai.providers.deepseek_provider import DeepSeekProvider

            provider = DeepSeekProvider(
                api_key="test-key",
                base_url="https://api.deepseek.com",
                model_name="deepseek-chat",
            )
        finally:
            http_patcher.stop()

        factory = CircuitBreakerFactory(_mock_redis())
        router = ModelRouter(factory)

        with (
            override_settings(EVENT_BUS_IMPLEMENTATION="fake"),
            patch(
                "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.CircuitBreakerFactory",
                return_value=factory,
            ),
            patch(
                "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider",
                return_value=provider,
            ),
            patch(
                "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter",
                return_value=router,
            ),
            patch(
                "apps.ai_engine.model_router.config",
                ai_provider_priority=["deepseek"], ai_provider_disabled=set(), ai_cost_tier_ceilings={}, ai_routing_fast_tier_threshold_ms=1500,
            ),
            patch(
                "apps.ai_engine.infrastructure.ai_reasoning_orchestrator.MarketContextCache"
            ) as mock_cache_cls,
        ):
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            reset_event_bus()
            bus = get_event_bus()
            register_recommendation_handlers(bus)

            orchestrator = AIReasoningOrchestrator()
            result = orchestrator.orchestrate(event)

            assert result is not None
            assert result["symbol"] == "RELIANCE"
            assert result["direction"] == "BUY"

            published = [e.event_type for e in bus.published_events]
            assert "ai_engine.RecommendationIssued" in published

            recommendation = Recommendation.objects.filter(
                symbol="RELIANCE",
                provider="deepseek",
                correlation_id=correlation_id,
            ).first()
            assert recommendation is not None
            assert recommendation.direction == "BUY"
