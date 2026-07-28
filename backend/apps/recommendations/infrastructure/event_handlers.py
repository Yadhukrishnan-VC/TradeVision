from __future__ import annotations

from collections.abc import Callable

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.recommendations.infrastructure.tasks import create_recommendation


def _handle_recommendation_issued(event: DomainEvent) -> None:
    payload = event.payload
    create_recommendation.delay(
        symbol=payload["symbol"],
        direction=payload.get("direction", "WATCH"),
        confidence_score=str(payload.get("confidence_score", "0.70")),
        strategy_id=payload.get("strategy_id"),
        confidence_evaluation_id=payload.get("confidence_evaluation_id"),
        analysis_event_id=payload.get("analysis_event_id"),
        reason=payload.get("reasoning", ""),
        risk_level=payload.get("risk_level", "MEDIUM"),
        risk_explanation=payload.get("risk_explanation", ""),
        key_factors=payload.get("key_factors", []),
        time_horizon=payload.get("time_horizon", "SHORT"),
        provider=payload.get("provider", "fallback"),
        validated_response=payload.get("validated_response", {}),
        correlation_id=str(event.correlation_id),
    )


SUBSCRIBED_EVENTS: dict[str, list[Callable[[DomainEvent], None]]] = {
    "ai_engine.RecommendationIssued": [_handle_recommendation_issued],
}


def register_handlers(event_bus: EventBus) -> None:
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            event_bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group="recommendations",
            )
