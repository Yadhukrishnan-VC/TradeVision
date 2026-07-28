from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.recommendations.infrastructure.event_handlers import (
    SUBSCRIBED_EVENTS,
    _handle_recommendation_issued,
    register_handlers,
)


class TestEventHandlers:
    def test_subscribed_events_contains_recommendation_issued(self) -> None:
        assert "ai_engine.RecommendationIssued" in SUBSCRIBED_EVENTS

    def test_recommendation_issued_has_one_handler(self) -> None:
        handlers = SUBSCRIBED_EVENTS["ai_engine.RecommendationIssued"]
        assert len(handlers) == 1
        assert handlers[0] is _handle_recommendation_issued

    @patch("apps.recommendations.infrastructure.event_handlers.create_recommendation")
    def test_handle_recommendation_issued_dispatches_task(self, mock_create_recommendation) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="ai_engine.RecommendationIssued",
            payload={
                "symbol": "RELIANCE",
                "direction": "BUY",
                "confidence_score": "0.85",
                "strategy_id": "strat-123",
                "confidence_evaluation_id": "eval-456",
                "analysis_event_id": "evt-789",
                "reasoning": "Strong bullish signal",
                "risk_level": "LOW",
                "risk_explanation": "Low risk profile",
                "key_factors": [],
                "time_horizon": "SHORT",
                "provider": "deepseek",
                "validated_response": {"recommendation_id": "", "trade_explanation": "test", "risk_explanation": "test"},
            },
            correlation_id=cid,
        )

        _handle_recommendation_issued(event)

        mock_create_recommendation.delay.assert_called_once_with(
            symbol="RELIANCE",
            direction="BUY",
            confidence_score="0.85",
            strategy_id="strat-123",
            confidence_evaluation_id="eval-456",
            analysis_event_id="evt-789",
            reason="Strong bullish signal",
            risk_level="LOW",
            risk_explanation="Low risk profile",
            key_factors=[],
            time_horizon="SHORT",
            provider="deepseek",
            validated_response={"recommendation_id": "", "trade_explanation": "test", "risk_explanation": "test"},
            correlation_id=str(event.correlation_id),
        )

    @patch("apps.recommendations.infrastructure.event_handlers.create_recommendation")
    def test_handle_recommendation_issued_without_optional_fields(self, mock_create_recommendation) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="ai_engine.RecommendationIssued",
            payload={
                "symbol": "TCS",
            },
            correlation_id=cid,
        )

        _handle_recommendation_issued(event)

        mock_create_recommendation.delay.assert_called_once_with(
            symbol="TCS",
            direction="WATCH",
            confidence_score="0.70",
            strategy_id=None,
            confidence_evaluation_id=None,
            analysis_event_id=None,
            reason="",
            risk_level="MEDIUM",
            risk_explanation="",
            key_factors=[],
            time_horizon="SHORT",
            provider="fallback",
            validated_response={},
            correlation_id=str(event.correlation_id),
        )

    def test_register_handlers_subscribes_to_event_bus(self) -> None:
        bus = MagicMock()

        register_handlers(bus)

        bus.subscribe.assert_called_once_with(
            event_type="ai_engine.RecommendationIssued",
            handler=_handle_recommendation_issued,
            consumer_group="recommendations",
        )

    def test_register_handlers_with_mocked_subscribe(self) -> None:
        bus = MagicMock()

        register_handlers(bus)

        bus.subscribe.assert_called_once()
        call_args = bus.subscribe.call_args
        assert call_args[1]["event_type"] == "ai_engine.RecommendationIssued"
        assert call_args[1]["consumer_group"] == "recommendations"
