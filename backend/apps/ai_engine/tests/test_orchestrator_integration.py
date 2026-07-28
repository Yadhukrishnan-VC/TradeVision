from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import override_settings

from apps.ai_engine.infrastructure.ai_reasoning_orchestrator import (
    AIReasoningOrchestrator,
)
from apps.eventbus.domain.events import DomainEvent
from core.ai.exceptions import AIConnectionError


class TestOrchestratorIntegration:
    def test_orchestrator_recommendation_contains_real_provider_name(self) -> None:
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "RELIANCE",
                "rule_id": "price_movement_rule",
                "event_type": "price_movement",
                "trigger_data": {"change_pct": "3.5"},
                "analysis_event_id": str(uuid.uuid4()),
            },
            correlation_id=uuid.uuid4(),
        )

        with (
            patch.object(AIReasoningOrchestrator, "_match_strategy") as mock_match,
            patch.object(AIReasoningOrchestrator, "_render_prompt") as mock_render,
            patch.object(AIReasoningOrchestrator, "_validate_response") as mock_validate,
            patch.object(AIReasoningOrchestrator, "_evaluate_confidence") as mock_conf,
        ):
            mock_match.return_value = None
            mock_render.return_value = "test prompt"

            valid_response = MagicMock()
            valid_response.direction = "BUY"
            valid_response.confidence_score = 0.85
            valid_response.reasoning = "Strong technical setup with sufficient length"
            valid_response.risk_level = "LOW"
            valid_response.risk_explanation = "Risk explanation with sufficient length"
            valid_response.key_factors = ("RSI bullish",)
            valid_response.contradicting_factors = ()
            valid_response.time_horizon = "SHORT"
            valid_response.follow_up_triggers = ()
            mock_validate.return_value = valid_response

            mock_conf_result = MagicMock()
            mock_conf_result.adjusted_confidence = 0.85
            mock_conf_result.confidence_evaluation_id = "eval-123"
            mock_conf.return_value = mock_conf_result

            mock_bus = MagicMock()
            with (
                patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.get_event_bus") as mock_get_bus,
                patch.object(AIReasoningOrchestrator, "_call_ai") as mock_call_ai,
            ):
                mock_get_bus.return_value = mock_bus

                from core.ai.base_provider import AIRawResponse

                mock_call_ai.return_value = AIRawResponse(
                    request_id=uuid.uuid4(),
                    provider="deepseek",
                    raw_text=json.dumps({
                        "direction": "BUY",
                        "confidence_score": 0.85,
                        "reasoning": "Strong technical setup with sufficient length for reasoning",
                        "risk_level": "LOW",
                        "risk_explanation": "Risk explanation with sufficient length for validation",
                        "key_factors": ["RSI bullish"],
                        "contradicting_factors": [],
                        "time_horizon": "SHORT",
                        "follow_up_triggers": [],
                    }),
                    input_tokens=100,
                    output_tokens=50,
                    latency_ms=1200.0,
                    estimated_cost_usd=Decimal("0.001"),
                    timestamp=datetime.now(timezone.utc),
                )

                orchestrator = AIReasoningOrchestrator()
                result = orchestrator.orchestrate(event)

                assert result is not None
                assert mock_bus.publish.called
                published_event = mock_bus.publish.call_args[0][0]
                assert published_event.payload["provider"] == "deepseek"
                assert published_event.payload["direction"] == "BUY"

    def test_fallback_reasoning_contains_production_wording(self) -> None:
        with (
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider") as mock_factory,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter") as mock_router_cls,
        ):
            mock_provider = MagicMock()
            mock_provider.complete.side_effect = AIConnectionError("Simulated connection error")
            mock_factory.return_value = mock_provider

            mock_router = MagicMock()
            mock_decision = MagicMock()
            mock_decision.selected_provider.value = "deepseek"
            mock_router.route.return_value = mock_decision
            mock_router_cls.return_value = mock_router

            orchestrator = AIReasoningOrchestrator()
            result = orchestrator._call_ai("test prompt", "RELIANCE", uuid.uuid4())

            assert result is not None
            assert result.provider == "fallback"
            import json
            parsed = json.loads(result.raw_text)
            assert "AI provider unavailable" in parsed["reasoning"]
            assert "AI provider not yet implemented" not in parsed["reasoning"]

    def test_call_ai_returns_fallback_when_provider_raises_connection_error(self) -> None:
        with (
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider") as mock_factory,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter") as mock_router_cls,
        ):
            mock_provider = MagicMock()
            mock_provider.complete.side_effect = AIConnectionError("Simulated connection error")
            mock_factory.return_value = mock_provider

            mock_router = MagicMock()
            mock_decision = MagicMock()
            mock_decision.selected_provider.value = "deepseek"
            mock_router.route.return_value = mock_decision
            mock_router_cls.return_value = mock_router

            orchestrator = AIReasoningOrchestrator()
            result = orchestrator._call_ai("test prompt", "RELIANCE", uuid.uuid4())

            assert result is not None
            assert result.provider == "fallback"
            assert result.raw_text is not None

    def test_call_ai_returns_real_response_when_provider_succeeds(self) -> None:
        with (
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider") as mock_factory,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter") as mock_router_cls,
        ):
            from core.ai.base_provider import AIRawResponse

            expected_response = AIRawResponse(
                request_id=uuid.uuid4(),
                provider="deepseek",
                raw_text=json.dumps({
                    "direction": "BUY",
                    "confidence_score": 0.85,
                    "reasoning": "Strong technical setup with sufficient length for reasoning",
                    "risk_level": "LOW",
                    "risk_explanation": "Risk explanation with sufficient length for validation",
                    "key_factors": ["RSI bullish", "Volume spike"],
                    "contradicting_factors": [],
                    "time_horizon": "SHORT",
                    "follow_up_triggers": [],
                }),
                input_tokens=100,
                output_tokens=50,
                latency_ms=1200.0,
                estimated_cost_usd=Decimal("0.001"),
                timestamp=datetime.now(timezone.utc),
            )

            mock_provider = MagicMock()
            mock_provider.complete.return_value = expected_response
            mock_factory.return_value = mock_provider

            mock_router = MagicMock()
            mock_decision = MagicMock()
            mock_decision.selected_provider.value = "deepseek"
            mock_router.route.return_value = mock_decision
            mock_router_cls.return_value = mock_router

            orchestrator = AIReasoningOrchestrator()
            result = orchestrator._call_ai("test prompt", "RELIANCE", uuid.uuid4())

            assert result is not None
            assert result.provider == "deepseek"
            assert result.raw_text is not None
            parsed = json.loads(result.raw_text)
            assert parsed["direction"] == "BUY"

    def test_call_ai_returns_none_on_unexpected_error(self) -> None:
        with (
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider") as mock_factory,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter") as mock_router_cls,
        ):
            mock_provider = MagicMock()
            mock_provider.complete.side_effect = ValueError("Unexpected catastrophic failure")
            mock_factory.return_value = mock_provider

            mock_router = MagicMock()
            mock_decision = MagicMock()
            mock_decision.selected_provider.value = "deepseek"
            mock_router.route.return_value = mock_decision
            mock_router_cls.return_value = mock_router

            orchestrator = AIReasoningOrchestrator()
            result = orchestrator._call_ai("test prompt", "RELIANCE", uuid.uuid4())

            assert result is None

