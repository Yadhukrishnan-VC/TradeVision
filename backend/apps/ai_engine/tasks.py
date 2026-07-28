from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="tradevision.ai_engine.evaluate_confidence",
    queue="ai_reasoning",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def evaluate_confidence(
    self,
    raw_confidence: float,
    packet_id: str,
    strategy_data: dict | None = None,
    packet_data: dict | None = None,
) -> dict:
    from django.conf import settings

    if not getattr(settings, "CONFIDENCE_ENGINE_V2_ENABLED", False):
        return {
            "raw_confidence": raw_confidence,
            "adjusted_confidence": raw_confidence,
            "threshold_met": True,
            "adjustment_reasons": ["confidence_engine_v2_disabled"],
        }

    from apps.ai_engine.services import ConfidenceEngine
    from apps.strategy_registry.models import TradingStrategy

    strategy = None
    if strategy_data:
        try:
            strategy = TradingStrategy.objects.get(id=strategy_data.get("strategy_id"))
        except TradingStrategy.DoesNotExist:
            logger.warning(
                "strategy_not_found_for_confidence",
                extra={"strategy_id": strategy_data.get("strategy_id")},
            )

    engine = ConfidenceEngine()
    result = engine.evaluate_and_persist(
        raw_confidence=raw_confidence,
        packet_id=packet_id,
        strategy=strategy,
        packet=None,
    )

    return {
        "raw_confidence": result.raw_confidence,
        "adjusted_confidence": result.adjusted_confidence,
        "threshold_met": result.threshold_met,
        "adjustment_reasons": result.adjustment_reasons,
    }


@shared_task(
    name="tradevision.ai_engine.route_and_render",
    queue="ai_reasoning",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def route_and_render(
    self,
    strategy_match_result: dict,
) -> dict | None:
    from core.ai.exceptions import NoAvailableProviderError
    from core.config import config
    from core.constants import AIProviderName
    from core.events.event_types import EventType
    from core.redis_client import get_redis_client
    from core.resilience.circuit_breaker import CircuitBreakerFactory

    from apps.ai_engine.model_router import (
        ModelRouter,
        RoutingCapabilityRequirements,
        RoutingRequest,
    )
    from apps.ai_engine.prompt_manager.service import PromptManager

    event_type_str = strategy_match_result.get("event_type", "price_movement")
    try:
        event_type = EventType(event_type_str)
    except ValueError:
        logger.error(
            "invalid_event_type",
            extra={"event_type": event_type_str},
        )
        return None

    caps = RoutingCapabilityRequirements(requires_structured_json=True)
    request = RoutingRequest(
        event_type=event_type,
        required_capabilities=caps,
        preferred_provider=(
            AIProviderName(strategy_match_result["preferred_provider"])
            if strategy_match_result.get("preferred_provider")
            else None
        ),
    )

    cb_factory = CircuitBreakerFactory(get_redis_client())
    router = ModelRouter(cb_factory)

    try:
        decision = router.route(request)
    except NoAvailableProviderError:
        logger.error(
            "no_available_provider",
            extra={"event_type": event_type_str},
        )
        return None

    pm = PromptManager()
    try:
        prompt = pm.render(event_type=event_type.value)
    except ValueError as exc:
        logger.error(
            "prompt_render_failed",
            extra={"event_type": event_type_str, "error": str(exc)},
        )
        return None

    return {
        "selected_provider": decision.selected_provider.value,
        "selected_model": decision.selected_model,
        "rendered_prompt": prompt,
        "fallback_chain": [p.value for p in decision.fallback_chain],
        "decision_trace": list(decision.decision_trace),
        "strategy_match": strategy_match_result,
    }
