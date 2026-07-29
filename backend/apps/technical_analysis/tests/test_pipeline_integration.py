from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
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
            "intelligence.PacketBuilt",
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
                "indicators": {"rsi_14": 62.5, "macd": 1.23, "bb_upper": 3600.0},
                "price": {"close": "3124.50", "high": "3145.00", "low": "3100.00", "open": "3110.00", "volume": "1234567"},
                "pine_id": "test",
                "pine_version": "5",
            },
            correlation_id=cid,
        )

        with patch("apps.eventbus.infrastructure.fake_event_bus.StoredEvent.objects.create"):
            handle_ta_completed(event)

            assert handler_called
            assert captured_event is not None
            assert captured_event.event_type == "intelligence.PacketBuilt"
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

    @override_settings(EVENT_BUS_IMPLEMENTATION="fake")
    def test_full_pipeline_ta_to_recommendation_uses_real_ai_provider(self) -> None:
        reset_event_bus()
        bus = get_event_bus()

        recommendation_issued = []
        def rec_handler(event: DomainEvent) -> None:
            recommendation_issued.append(event)

        bus.subscribe(
            "ai_engine.RecommendationIssued",
            rec_handler,
            consumer_group="test_full_pipeline",
        )

        cid = uuid.uuid4()
        ta_event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={
                "symbol": "RELIANCE",
                "snapshot_id": str(uuid.uuid4()),
                "exchange": "NSE",
                "timeframe": "1D",
                "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
                "indicators": {
                    "rsi_14": 62.5,
                    "macd": 1.23,
                    "bb_upper": 3600.0,
                    "bb_lower": 3400.0,
                    "ema_20": 3500.0,
                    "ema_50": 3450.0,
                    "ema_200": 3300.0,
                },
                "price": {
                    "close": "3520.00",
                    "high": "3550.00",
                    "low": "3480.00",
                    "open": "3490.00",
                    "volume": "1500000",
                    "prev_close": "3480.00",
                    "change_pct": "1.15",
                },
                "pine_id": "test_script",
                "pine_version": "5",
            },
            correlation_id=cid,
        )

        from apps.intelligence.infrastructure.ta_completed_handler import handle_ta_completed
        from apps.ai_engine.infrastructure.event_handlers import _handle_rule_fired

        with (
            patch("apps.eventbus.infrastructure.fake_event_bus.StoredEvent.objects.create"),
            patch("apps.intelligence.infrastructure.ta_completed_handler.TASnapshotRepository") as mock_repo,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIReasoningOrchestrator._match_strategy") as mock_match,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIReasoningOrchestrator._render_prompt") as mock_render,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIReasoningOrchestrator._validate_response") as mock_validate,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIReasoningOrchestrator._evaluate_confidence") as mock_conf,
        ):
            mock_repo.return_value.find_by_symbol.return_value = []

            mock_match.return_value = None
            mock_render.return_value = "test prompt for RELIANCE"

            valid = MagicMock()
            valid.direction = "BUY"
            valid.confidence_score = 0.85
            valid.reasoning = "Strong technical setup with sufficient length for validation"
            valid.risk_level = "LOW"
            valid.risk_explanation = "Risk explanation with sufficient length for validation"
            valid.key_factors = ("RSI bullish", "Volume spike")
            valid.contradicting_factors = ()
            valid.time_horizon = "SHORT"
            valid.follow_up_triggers = ()
            mock_validate.return_value = valid

            conf_result = MagicMock()
            conf_result.adjusted_confidence = 0.85
            conf_result.confidence_evaluation_id = "eval-full-pipeline"
            mock_conf.return_value = conf_result

            from core.ai.base_provider import AIRawResponse
            ai_response = AIRawResponse(
                request_id=uuid.uuid4(),
                provider="deepseek",
                raw_text='{"direction": "BUY", "confidence_score": 0.85, "reasoning": "Strong technical setup with sufficient length for reasoning", "risk_level": "LOW", "risk_explanation": "Risk explanation with sufficient length for validation", "key_factors": ["RSI bullish", "Volume spike"], "contradicting_factors": [], "time_horizon": "SHORT", "follow_up_triggers": []}',
                input_tokens=100,
                output_tokens=50,
                latency_ms=1200.0,
                estimated_cost_usd=Decimal("0.001"),
                timestamp=datetime.now(timezone.utc),
            )

            with (
                patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider") as mock_factory,
                patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter") as mock_router_cls,
            ):
                mock_provider = MagicMock()
                mock_provider.complete.return_value = ai_response
                mock_factory.return_value = mock_provider

                mock_router = MagicMock()
                mock_decision = MagicMock()
                mock_decision.selected_provider.value = "deepseek"
                mock_decision.fallback_chain = ()
                mock_router.route.return_value = mock_decision
                mock_router_cls.return_value = mock_router

                handle_ta_completed(ta_event)

                rule_event = DomainEvent.create(
                    event_type="rule_engine.RuleFired",
                    payload={
                        "symbol": "RELIANCE",
                        "rule_id": "price_movement_rule",
                        "event_type": "price_movement",
                        "trigger_data": {"change_pct": "1.15"},
                        "analysis_event_id": str(uuid.uuid4()),
                    },
                    correlation_id=cid,
                )
                _handle_rule_fired(rule_event)

                assert len(recommendation_issued) > 0
                published = recommendation_issued[0]
                assert published.payload["provider"] == "deepseek"
                assert published.payload["direction"] == "BUY"
                assert published.payload["symbol"] == "RELIANCE"
                assert published.correlation_id == cid

                mock_provider.complete.assert_called_once()

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
