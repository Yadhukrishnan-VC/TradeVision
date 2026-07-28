from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus, reset_event_bus


class TestPipelineIntegration:
    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_ta_completed_triggers_packet_enriched_event(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        handler_called = False
        captured_event = None

        def test_handler(event: DomainEvent) -> None:
            nonlocal handler_called, captured_event
            handler_called = True
            captured_event = event

        bus.subscribe(
            "intelligence.PacketEnriched",
            test_handler,
            consumer_group="test_pipeline",
        )

        from apps.intelligence.infrastructure.ta_completed_handler import handle_ta_completed

        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={
                "symbol": "RELIANCE",
                "snapshot_id": str(uuid.uuid4()),
                "exchange": "NSE",
                "timeframe": "1D",
                "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
                "indicator_keys": ["rsi", "macd"],
                "pine_id": "test",
                "pine_version": "5",
            },
            correlation_id=cid,
        )

        with patch("apps.intelligence.infrastructure.ta_completed_handler.IntelligenceService") as mock_intel:
            mock_intel.return_value = MagicMock()
            with patch("apps.eventbus.infrastructure.fake_event_bus.StoredEvent.objects.create"):
                handle_ta_completed(event)

            assert handler_called
            assert captured_event is not None
            assert captured_event.event_type == "intelligence.PacketEnriched"
            assert captured_event.payload["symbol"] == "RELIANCE"
            assert captured_event.correlation_id == cid

    def test_rule_fired_triggers_ai_engine_handler(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        handler_called = False

        def test_handler(event: DomainEvent) -> None:
            nonlocal handler_called
            handler_called = True

        bus.subscribe(
            "ai_engine.RecommendationIssued",
            test_handler,
            consumer_group="test_pipeline_ai",
        )

        from apps.ai_engine.infrastructure.event_handlers import _handle_rule_fired

        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "RELIANCE",
                "rule_id": "price_movement_rule",
                "event_type": "price_movement",
                "severity": "HIGH",
                "trigger_data": {"change_pct": "3.5"},
                "analysis_event_id": str(uuid.uuid4()),
            },
            correlation_id=uuid.uuid4(),
        )

        with patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIReasoningOrchestrator.orchestrate") as mock_orch:
            mock_orch.return_value = {"symbol": "RELIANCE", "direction": "BUY", "confidence_score": 0.85}
            _handle_rule_fired(event)
            mock_orch.assert_called_once_with(event)

    def test_recommendation_issued_triggers_recommendations_handler(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        from apps.recommendations.infrastructure.event_handlers import _handle_recommendation_issued

        event = DomainEvent.create(
            event_type="ai_engine.RecommendationIssued",
            payload={
                "symbol": "RELIANCE",
                "direction": "BUY",
                "confidence_score": "0.85",
                "strategy_id": "strat-123",
                "confidence_evaluation_id": "eval-456",
                "analysis_event_id": str(uuid.uuid4()),
                "reasoning": "Strong technical setup",
                "risk_level": "LOW",
                "risk_explanation": "Low risk",
                "key_factors": ["RSI bullish", "Volume spike"],
                "time_horizon": "SHORT",
                "provider": "deepseek",
                "validated_response": {"recommendation_id": "", "trade_explanation": "test", "risk_explanation": "test"},
            },
            correlation_id=uuid.uuid4(),
        )

        with patch("apps.recommendations.infrastructure.event_handlers.create_recommendation.delay") as mock_delay:
            _handle_recommendation_issued(event)
            mock_delay.assert_called_once()
            args, kwargs = mock_delay.call_args
            assert kwargs["symbol"] == "RELIANCE"
            assert kwargs["direction"] == "BUY"
