from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from django.conf import settings

from apps.ai_engine.model_router import ModelRouter, RoutingRequest
from apps.ai_engine.prompt_manager.service import PromptManager
from apps.ai_engine.services import ConfidenceEngine
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.strategy_registry.services import StrategyMatcher
from core.ai.base_provider import AIRecommendation, AIRequest, AIRawResponse
from core.ai.exceptions import (
    AIAuthenticationError,
    AIConnectionError,
    AIProviderError,
    AIQuotaExceededError,
    AIRateLimitError,
    AIResponseValidationError,
    AITimeoutError,
)
from core.ai.provider_factory import AIProviderFactory
from core.ai.signals import IntelligenceSignal, map_signal_to_recommendation
from core.ai.validator import AIResponseValidator
from core.events.event_types import EventType
from core.resilience.circuit_breaker import CircuitBreakerFactory
from core.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class AIReasoningOrchestrator:
    def __init__(self) -> None:
        self._strategy_matcher = StrategyMatcher()
        self._prompt_manager = PromptManager()
        self._confidence_engine = ConfidenceEngine()
        self._response_validator = AIResponseValidator()
        self._circuit_breaker_factory = CircuitBreakerFactory(get_redis_client())
        self._model_router = ModelRouter(self._circuit_breaker_factory)

    def orchestrate(self, event: DomainEvent) -> dict[str, Any] | None:
        payload = event.payload
        symbol = payload.get("symbol", "")

        if not symbol:
            logger.warning("orchestrator_missing_symbol", extra={"event_id": str(event.event_id)})
            return None

        correlation_id = event.correlation_id
        causation_id = event.event_id

        strategy = self._match_strategy(symbol)
        strategy_id = str(strategy.id) if strategy else None

        rendered_prompt = self._render_prompt(event, strategy)

        raw_response = self._call_ai(rendered_prompt, symbol, correlation_id)
        if raw_response is None:
            logger.error("ai_call_failed", extra={"symbol": symbol})
            return None

        validated = self._validate_response(raw_response)
        if validated is None:
            logger.error("ai_response_validation_failed", extra={"symbol": symbol})
            return None

        direction = validated.direction
        raw_confidence = validated.confidence_score

        confidence_result = self._evaluate_confidence(
            raw_confidence=raw_confidence,
            strategy=strategy,
            packet_id=str(causation_id),
        )

        recommendation_event = DomainEvent.create(
            event_type="ai_engine.RecommendationIssued",
            payload={
                "symbol": symbol,
                "direction": direction,
                "confidence_score": float(confidence_result.adjusted_confidence),
                "raw_confidence_score": raw_confidence,
                "strategy_id": strategy_id,
                "confidence_evaluation_id": confidence_result.confidence_evaluation_id,
                "analysis_event_id": str(causation_id),
                "reasoning": validated.reasoning,
                "risk_level": validated.risk_level,
                "risk_explanation": validated.risk_explanation,
                "key_factors": list(validated.key_factors),
                "contradicting_factors": list(validated.contradicting_factors),
                "time_horizon": validated.time_horizon,
                "follow_up_triggers": list(validated.follow_up_triggers),
                "provider": raw_response.provider,
                "event_type": payload.get("event_type", ""),
                "rule_id": payload.get("rule_id", ""),
                "trigger_data": payload.get("trigger_data", {}),
                "validated_response": {
                    "recommendation_id": "",
                    "trade_explanation": validated.reasoning,
                    "risk_explanation": validated.risk_explanation,
                },
            },
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

        try:
            bus = get_event_bus()
            bus.publish(recommendation_event)
            logger.info(
                "recommendation_issued",
                extra={
                    "symbol": symbol,
                    "direction": direction,
                    "confidence": float(confidence_result.adjusted_confidence),
                    "correlation_id": str(correlation_id),
                },
            )
        except Exception as exc:
            logger.exception(
                "recommendation_issue_failed",
                extra={"symbol": symbol, "error": str(exc)},
            )

        return {
            "symbol": symbol,
            "direction": direction,
            "confidence_score": float(confidence_result.adjusted_confidence),
            "strategy_id": strategy_id,
        }

    def _match_strategy(self, symbol: str) -> Any | None:
        try:
            packet_stub = type("PacketStub", (), {"symbol": symbol, "sector": None})()
            strategy = self._strategy_matcher.match(packet_stub)
            if strategy:
                logger.info(
                    "strategy_matched",
                    extra={"symbol": symbol, "strategy_id": str(strategy.id)},
                )
            return strategy
        except Exception as exc:
            logger.warning(
                "strategy_match_failed",
                extra={"symbol": symbol, "error": str(exc)},
            )
            return None

    def _render_prompt(self, event: DomainEvent, strategy: Any | None) -> str:
        signal_context: dict[str, Any] = {}
        try:
            payload = event.payload
            trigger_data = payload.get("trigger_data", {})
            signal_context = {
                "pine_output": json.dumps(trigger_data.get("indicators", {})),
                "market_regime": "UNKNOWN",
                "multi_timeframe_alignment": "NEUTRAL",
                "news_headlines": [],
                "sector_context": payload.get("sector_context", ""),
                "event": trigger_data,
            }
        except Exception as exc:
            logger.warning("prompt_context_assembly_failed", extra={"error": str(exc)})

        try:
            event_type_str = payload.get("event_type", "price_movement") if isinstance(payload := event.payload, dict) else "price_movement"
            prompt = self._prompt_manager.render(
                event_type=event_type_str,
                signal_context=signal_context,
            )
            return prompt
        except Exception as exc:
            logger.warning(
                "prompt_render_failed",
                extra={"error": str(exc)},
            )
            return "Analyze the following market data and provide a trading recommendation."

    def _call_ai(self, prompt: str, symbol: str, correlation_id: uuid.UUID) -> AIRawResponse | None:
        try:
            routing_request = RoutingRequest(
                event_type=EventType.PRICE_MOVEMENT,
                context_tokens_estimate=len(prompt.split()),
            )
            decision = self._model_router.route(routing_request)

            request = AIRequest(
                id=uuid.uuid4(),
                prompt=prompt,
                event_type=routing_request.event_type.value,
                symbol=symbol,
                prompt_version=self._prompt_manager.get_version("price_movement"),
                max_tokens=settings.AI_MAX_TOKENS,
                timestamp=datetime.now(timezone.utc),
            )

            provider = AIProviderFactory.get_provider(decision.selected_provider.value)
            raw_response = provider.complete(request)
            return raw_response

        except (AIAuthenticationError, AIProviderError, AIConnectionError,
                AITimeoutError, AIRateLimitError, AIQuotaExceededError) as exc:
            logger.warning(
                "ai_provider_error_using_fallback",
                extra={
                    "symbol": symbol,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            return self._fallback_response(request if 'request' in dir() else None, correlation_id, symbol)

        except Exception as exc:
            logger.exception(
                "ai_call_unexpected_error",
                extra={"symbol": symbol, "error": str(exc)},
            )
            return None

    def _fallback_response(
        self,
        request: AIRequest | None,
        correlation_id: uuid.UUID,
        symbol: str,
    ) -> AIRawResponse:
        return AIRawResponse(
            request_id=request.id if request else uuid.uuid4(),
            provider="fallback",
            raw_text=json.dumps({
                "direction": "WATCH",
                "confidence_score": 0.70,
                "reasoning": "Rule-based fallback: AI provider unavailable.",
                "risk_level": "MEDIUM",
                "risk_explanation": "Standard risk assessment based on rule engine trigger.",
                "key_factors": ["Rule engine triggered for " + symbol],
                "contradicting_factors": [],
                "time_horizon": "SHORT",
                "follow_up_triggers": ["Price movement beyond threshold"],
            }),
            input_tokens=0,
            output_tokens=0,
            latency_ms=0.0,
            estimated_cost_usd=Decimal("0.00"),
            timestamp=datetime.now(timezone.utc),
        )

    def _validate_response(self, raw_response: AIRawResponse) -> Any | None:
        try:
            return self._response_validator.validate(raw_response)
        except AIResponseValidationError as exc:
            logger.error(
                "ai_response_validation_failed",
                extra={
                    "provider": raw_response.provider,
                    "error": str(exc),
                },
            )
            return None

    def _evaluate_confidence(
        self,
        raw_confidence: float,
        strategy: Any | None,
        packet_id: str,
    ) -> Any:
        result = self._confidence_engine.evaluate_and_persist(
            raw_confidence=raw_confidence,
            packet_id=packet_id,
            strategy=strategy,
        )
        confidence_eval = None
        if result is not None and hasattr(result, 'adjusted_confidence'):
            from apps.ai_engine.models import ConfidenceEvaluation
            try:
                latest = ConfidenceEvaluation.objects.filter(packet_id=packet_id).order_by("-created_at").first()
                if latest:
                    confidence_eval = str(latest.id)
            except Exception:
                pass

        result.confidence_evaluation_id = confidence_eval
        return result
