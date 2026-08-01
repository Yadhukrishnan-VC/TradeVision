"""
Batch AI-5B — Recommendation provider identity + correlation_id persistence.

Integration coverage for fix #4:
    - create_from_ai_response persists provider and correlation_id on the
      Recommendation row (via the create_recommendation task path).
    - Defaults remain "fallback"/None when not supplied.
    - The event-handler → task wiring forwards both fields.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.recommendations.infrastructure.models import Recommendation

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_event_bus():
    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus

    reset_event_bus()


class TestRecommendationProviderIdentity:
    def test_create_from_ai_response_persists_provider_and_correlation_id(self, symbol) -> None:
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService

        correlation_id = uuid.uuid4()
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction="BUY",
            confidence_score=Decimal("0.80"),
            provider="deepseek",
            correlation_id=correlation_id,
        )

        saved = Recommendation.objects.get(id=aggregate.id)
        assert saved.provider == "deepseek"
        assert saved.correlation_id == correlation_id

    def test_create_defaults_to_fallback_provider(self, symbol) -> None:
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService

        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction="WATCH",
            confidence_score=Decimal("0.70"),
        )

        saved = Recommendation.objects.get(id=aggregate.id)
        assert saved.provider == "fallback"
        assert saved.correlation_id is None

    def test_aggregate_carries_provider_and_correlation_id(self, symbol) -> None:
        from apps.recommendations.application.recommendation_command_service import RecommendationCommandService

        correlation_id = uuid.uuid4()
        service = RecommendationCommandService()
        aggregate = service.create_from_ai_response(
            symbol=symbol,
            direction="BUY",
            confidence_score=Decimal("0.80"),
            provider="deepseek",
            correlation_id=correlation_id,
        )

        assert aggregate.provider == "deepseek"
        assert aggregate.correlation_id == correlation_id

    def test_create_recommendation_task_forwards_provider_and_correlation_id(self, symbol) -> None:
        from apps.recommendations.infrastructure.tasks import create_recommendation

        correlation_id = uuid.uuid4()
        with patch(
            "apps.recommendations.application.recommendation_command_service.RecommendationCommandService"
        ) as mock_service_cls:
            mock_aggregate = type(
                "Agg",
                (),
                {"id": uuid.uuid4(), "symbol": symbol, "direction": "BUY", "status": "DRAFT"},
            )()
            mock_service = mock_service_cls.return_value
            mock_service.create_from_ai_response.return_value = mock_aggregate

            with patch("apps.recommendations.infrastructure.tasks.compose_explanation.delay") as mock_compose:
                result = create_recommendation(
                    symbol=symbol,
                    direction="BUY",
                    confidence_score="0.80",
                    provider="deepseek",
                    correlation_id=str(correlation_id),
                    validated_response={"recommendation_id": str(mock_aggregate.id)},
                )

            assert result["recommendation_id"] == str(mock_aggregate.id)
            call_kwargs = mock_service.create_from_ai_response.call_args[1]
            assert call_kwargs["provider"] == "deepseek"
            assert call_kwargs["correlation_id"] == correlation_id
            assert mock_compose.called

    def test_event_handler_forwards_provider_and_correlation_id(self, symbol) -> None:
        from apps.recommendations.infrastructure.event_handlers import (
            _handle_recommendation_issued,
        )

        correlation_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="ai_engine.RecommendationIssued",
            payload={
                "symbol": symbol,
                "direction": "BUY",
                "confidence_score": "0.80",
                "strategy_id": None,
                "confidence_evaluation_id": None,
                "analysis_event_id": str(uuid.uuid4()),
                "reasoning": "Strong setup",
                "risk_level": "LOW",
                "risk_explanation": "None",
                "key_factors": [],
                "time_horizon": "SHORT",
                "provider": "deepseek",
                "validated_response": {},
            },
            correlation_id=correlation_id,
        )

        with patch("apps.recommendations.infrastructure.event_handlers.create_recommendation.delay") as mock_delay:
            _handle_recommendation_issued(event)

            call_kwargs = mock_delay.call_args[1]
            assert call_kwargs["provider"] == "deepseek"
            assert call_kwargs["correlation_id"] == str(correlation_id)
