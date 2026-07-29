from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from apps.ai_engine.infrastructure.ai_reasoning_orchestrator import (
    AIReasoningOrchestrator,
)
from apps.eventbus.domain.events import DomainEvent
from core.constants import AIProviderName


class TestAIReasoningOrchestrator:
    def test_orchestrate_missing_symbol_returns_none(self) -> None:
        orchestrator = AIReasoningOrchestrator()
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        result = orchestrator.orchestrate(event)
        assert result is None

    def test_orchestrate_publishes_recommendation_issued(self) -> None:
        orchestrator = AIReasoningOrchestrator()
        cid = uuid.uuid4()
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
            correlation_id=cid,
        )

        with patch.object(AIReasoningOrchestrator, "_match_strategy") as mock_match:
            mock_match.return_value = None
            with patch.object(AIReasoningOrchestrator, "_render_prompt") as mock_render:
                mock_render.return_value = "test prompt"
                with patch.object(AIReasoningOrchestrator, "_call_ai") as mock_ai:
                    mock_raw = MagicMock()
                    mock_raw.provider = "test_provider"
                    mock_raw.raw_text = '{"direction": "BUY", "confidence_score": 0.85, "reasoning": "Test reasoning with sufficient length", "risk_level": "LOW", "risk_explanation": "Test risk explanation sufficient length", "key_factors": ["factor1"], "contradicting_factors": [], "time_horizon": "SHORT", "follow_up_triggers": []}'
                    mock_ai.return_value = mock_raw
                    with patch.object(AIReasoningOrchestrator, "_validate_response") as mock_validate:
                        mock_validated = MagicMock()
                        mock_validated.direction = "BUY"
                        mock_validated.confidence_score = 0.85
                        mock_validated.reasoning = "Test reasoning"
                        mock_validated.risk_level = "LOW"
                        mock_validated.risk_explanation = "Test risk explanation"
                        mock_validated.key_factors = ("factor1",)
                        mock_validated.contradicting_factors = ()
                        mock_validated.time_horizon = "SHORT"
                        mock_validated.follow_up_triggers = ()
                        mock_validate.return_value = mock_validated
                        with patch.object(AIReasoningOrchestrator, "_evaluate_confidence") as mock_conf:
                            mock_conf_result = MagicMock()
                            mock_conf_result.adjusted_confidence = 0.85
                            mock_conf_result.confidence_evaluation_id = "eval-123"
                            mock_conf.return_value = mock_conf_result
                            with patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.get_event_bus") as mock_get_bus:
                                mock_bus = MagicMock()
                                mock_get_bus.return_value = mock_bus

                                result = orchestrator.orchestrate(event)

                                assert result is not None
                                assert result["symbol"] == "RELIANCE"
                                assert result["direction"] == "BUY"

                                assert mock_bus.publish.called
                                published_event = mock_bus.publish.call_args[0][0]
                                assert published_event.event_type == "ai_engine.RecommendationIssued"
                                assert published_event.correlation_id == cid
                                assert published_event.causation_id == event.event_id

    def test_orchestrate_handles_ai_failure_gracefully(self) -> None:
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "RELIANCE",
                "rule_id": "price_movement_rule",
                "event_type": "price_movement",
                "trigger_data": {},
                "analysis_event_id": str(uuid.uuid4()),
            },
            correlation_id=uuid.uuid4(),
        )

        with patch.object(AIReasoningOrchestrator, "_match_strategy") as mock_match:
            mock_match.return_value = None
            with patch.object(AIReasoningOrchestrator, "_render_prompt") as mock_render:
                mock_render.return_value = "test prompt"
                with patch.object(AIReasoningOrchestrator, "_call_ai") as mock_ai:
                    mock_ai.return_value = None

                    result = orchestrator_instance().orchestrate(event)
                    assert result is None


    def test_orchestrate_non_price_movement_event_type_reaches_router(self) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "RELIANCE",
                "rule_id": "volume_spike_rule",
                "event_type": "volume_spike",
                "severity": "HIGH",
                "trigger_data": {"volume_surge_pct": "250"},
                "analysis_event_id": str(uuid.uuid4()),
            },
            correlation_id=cid,
        )

        captured_request = {}

        def capture_route(request):
            captured_request["routing"] = request
            decision = MagicMock()
            decision.selected_provider.value = "deepseek"
            decision.fallback_chain = ()
            return decision

        with (
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider") as mock_factory,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter") as mock_router_cls,
            patch.object(AIReasoningOrchestrator, "_render_prompt") as mock_render,
            patch.object(AIReasoningOrchestrator, "_validate_response") as mock_validate,
            patch.object(AIReasoningOrchestrator, "_evaluate_confidence") as mock_conf,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.get_event_bus") as mock_get_bus,
        ):
            mock_provider = MagicMock()
            mock_provider.complete.return_value = MagicMock()
            mock_factory.return_value = mock_provider

            mock_router = MagicMock()
            mock_router.route.side_effect = capture_route
            mock_router_cls.return_value = mock_router

            mock_render.return_value = "test prompt"

            valid = MagicMock()
            valid.direction = "BUY"
            valid.confidence_score = 0.85
            valid.reasoning = "Test reasoning with sufficient length for validation"
            valid.risk_level = "LOW"
            valid.risk_explanation = "Risk explanation sufficient for validation"
            valid.key_factors = ("Volume spike",)
            valid.contradicting_factors = ()
            valid.time_horizon = "SHORT"
            valid.follow_up_triggers = ()
            mock_validate.return_value = valid

            conf_result = MagicMock()
            conf_result.adjusted_confidence = 0.85
            conf_result.confidence_evaluation_id = "eval-volume"
            mock_conf.return_value = conf_result

            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            orchestrator = AIReasoningOrchestrator()
            result = orchestrator.orchestrate(event)

            assert result is not None
            assert captured_request["routing"].event_type.value == "volume_spike"

    def test_orchestrate_wires_strategy_preferred_provider_to_router(self) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "RELIANCE",
                "rule_id": "announcement_rule",
                "event_type": "announcement",
                "trigger_data": {},
                "analysis_event_id": str(uuid.uuid4()),
            },
            correlation_id=cid,
        )

        captured_request = {}

        def capture_route(request):
            captured_request["routing"] = request
            decision = MagicMock()
            decision.selected_provider.value = "deepseek"
            decision.fallback_chain = ()
            return decision

        strategy = MagicMock()
        strategy.id = uuid.uuid4()
        strategy.preferred_provider = "gemini"

        with (
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider") as mock_factory,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter") as mock_router_cls,
            patch.object(AIReasoningOrchestrator, "_match_strategy") as mock_match,
            patch.object(AIReasoningOrchestrator, "_render_prompt") as mock_render,
            patch.object(AIReasoningOrchestrator, "_validate_response") as mock_validate,
            patch.object(AIReasoningOrchestrator, "_evaluate_confidence") as mock_conf,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.get_event_bus") as mock_get_bus,
        ):
            mock_provider = MagicMock()
            mock_provider.complete.return_value = MagicMock()
            mock_factory.return_value = mock_provider

            mock_router = MagicMock()
            mock_router.route.side_effect = capture_route
            mock_router_cls.return_value = mock_router

            mock_match.return_value = strategy
            mock_render.return_value = "test prompt"

            valid = MagicMock()
            valid.direction = "WATCH"
            valid.confidence_score = 0.70
            valid.reasoning = "Test reasoning with sufficient length for validation"
            valid.risk_level = "MEDIUM"
            valid.risk_explanation = "Risk explanation sufficient for validation"
            valid.key_factors = ("Announcement",)
            valid.contradicting_factors = ()
            valid.time_horizon = "SHORT"
            valid.follow_up_triggers = ()
            mock_validate.return_value = valid

            conf_result = MagicMock()
            conf_result.adjusted_confidence = 0.70
            conf_result.confidence_evaluation_id = "eval-announce"
            mock_conf.return_value = conf_result

            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            orchestrator = AIReasoningOrchestrator()
            result = orchestrator.orchestrate(event)

            assert result is not None
            assert captured_request["routing"].event_type.value == "announcement"
            assert captured_request["routing"].preferred_provider == AIProviderName.GEMINI


    def test_render_prompt_cache_hit_populates_scores(self) -> None:
        from unittest.mock import PropertyMock

        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "RELIANCE",
                "event_type": "price_movement",
                "trigger_data": {"indicators": {"rsi_14": 62.5}},
            },
            correlation_id=cid,
        )

        mock_context = MagicMock()
        mock_context.market_regime = type("MR", (), {"value": "BULLISH"})()
        mock_context.multi_timeframe_alignment = type("MTF", (), {"value": "BULLISH_ALIGNED"})()
        mock_context.bullishness_score = 0.74
        mock_context.bearishness_score = 0.11
        mock_context.volatility_score = 0.32
        mock_context.trend_score = 0.68
        mock_context.liquidity_score = 0.81
        mock_context.momentum_score = 0.63
        mock_context.overall_context_confidence = 0.88
        mock_context.pattern_alignment_note = "PATTERN_ENGINE_NOT_AVAILABLE"

        with (
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.MarketContextCache") as mock_cache_cls,
            patch.object(AIReasoningOrchestrator, "_match_strategy") as mock_match,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.PromptManager") as mock_pm_cls,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.get_event_bus") as mock_get_bus,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter") as mock_router_cls,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider") as mock_factory,
            patch.object(AIReasoningOrchestrator, "_validate_response") as mock_validate,
            patch.object(AIReasoningOrchestrator, "_evaluate_confidence") as mock_conf,
        ):
            mock_cache = MagicMock()
            mock_cache.get.return_value = mock_context
            mock_cache_cls.return_value = mock_cache

            mock_match.return_value = None

            mock_pm = MagicMock()
            mock_pm.render.return_value = "rendered prompt"
            mock_pm_cls.return_value = mock_pm

            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            mock_router = MagicMock()
            decision = MagicMock()
            decision.selected_provider.value = "deepseek"
            decision.fallback_chain = ()
            mock_router.route.return_value = decision
            mock_router_cls.return_value = mock_router

            mock_provider = MagicMock()
            mock_provider.complete.return_value = MagicMock()
            mock_factory.return_value = mock_provider

            valid = MagicMock()
            valid.direction = "BUY"
            valid.confidence_score = 0.85
            valid.reasoning = "Test reasoning with sufficient length for validation"
            valid.risk_level = "LOW"
            valid.risk_explanation = "Risk explanation sufficient for validation"
            valid.key_factors = ("factor1",)
            valid.contradicting_factors = ()
            valid.time_horizon = "SHORT"
            valid.follow_up_triggers = ()
            mock_validate.return_value = valid

            conf_result = MagicMock()
            conf_result.adjusted_confidence = 0.85
            conf_result.confidence_evaluation_id = "eval-cache-hit"
            mock_conf.return_value = conf_result

            orchestrator = AIReasoningOrchestrator()
            result = orchestrator.orchestrate(event)

            assert result is not None
            assert mock_cache.get.called
            assert mock_cache.get.call_args[0][0] == "RELIANCE"

            assert mock_pm.render.called
            rendered_kwargs = mock_pm.render.call_args[1]
            ctx = rendered_kwargs["signal_context"]
            assert ctx["market_regime"] == "BULLISH"
            assert ctx["bullishness_score"] == 0.74
            assert ctx["overall_context_confidence"] == 0.88

    def test_render_prompt_cache_miss_uses_unknown_defaults(self) -> None:
        cid = uuid.uuid4()
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload={
                "symbol": "RELIANCE",
                "event_type": "price_movement",
                "trigger_data": {"indicators": {"rsi_14": 62.5}},
            },
            correlation_id=cid,
        )

        with (
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.MarketContextCache") as mock_cache_cls,
            patch.object(AIReasoningOrchestrator, "_match_strategy") as mock_match,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.PromptManager") as mock_pm_cls,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.get_event_bus") as mock_get_bus,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.ModelRouter") as mock_router_cls,
            patch("apps.ai_engine.infrastructure.ai_reasoning_orchestrator.AIProviderFactory.get_provider") as mock_factory,
            patch.object(AIReasoningOrchestrator, "_validate_response") as mock_validate,
            patch.object(AIReasoningOrchestrator, "_evaluate_confidence") as mock_conf,
        ):
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_cls.return_value = mock_cache

            mock_match.return_value = None

            mock_pm = MagicMock()
            mock_pm.render.return_value = "rendered prompt"
            mock_pm_cls.return_value = mock_pm

            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            mock_router = MagicMock()
            decision = MagicMock()
            decision.selected_provider.value = "deepseek"
            decision.fallback_chain = ()
            mock_router.route.return_value = decision
            mock_router_cls.return_value = mock_router

            mock_provider = MagicMock()
            mock_provider.complete.return_value = MagicMock()
            mock_factory.return_value = mock_provider

            valid = MagicMock()
            valid.direction = "WATCH"
            valid.confidence_score = 0.70
            valid.reasoning = "Test reasoning with sufficient length for validation"
            valid.risk_level = "MEDIUM"
            valid.risk_explanation = "Risk explanation sufficient for validation"
            valid.key_factors = ("Default",)
            valid.contradicting_factors = ()
            valid.time_horizon = "SHORT"
            valid.follow_up_triggers = ()
            mock_validate.return_value = valid

            conf_result = MagicMock()
            conf_result.adjusted_confidence = 0.70
            conf_result.confidence_evaluation_id = "eval-cache-miss"
            mock_conf.return_value = conf_result

            orchestrator = AIReasoningOrchestrator()
            result = orchestrator.orchestrate(event)

            assert result is not None

            assert mock_pm.render.called
            rendered_kwargs = mock_pm.render.call_args[1]
            ctx = rendered_kwargs["signal_context"]
            assert ctx["market_regime"] == "UNKNOWN"
            assert ctx["bullishness_score"] == 0.0
            assert ctx["overall_context_confidence"] == 0.0


def orchestrator_instance() -> AIReasoningOrchestrator:
    return AIReasoningOrchestrator()
