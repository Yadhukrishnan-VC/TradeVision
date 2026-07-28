from __future__ import annotations

from collections.abc import Callable

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.trader_memory.infrastructure.tasks import record_memory_entry


def _handle_recommendation_event(event: DomainEvent) -> None:
    record_memory_entry.delay(
        recommendation_id=event.payload["recommendation_id"],
        event_type=event.event_type,
        payload=event.payload,
        occurred_at=event.occurred_at.isoformat(),
        correlation_id=str(event.correlation_id),
    )


SUBSCRIBED_EVENTS: dict[str, list[Callable[[DomainEvent], None]]] = {
    "recommendations.RecommendationCreated": [_handle_recommendation_event],
    "recommendations.RecommendationStatusChanged": [_handle_recommendation_event],
}


def register_handlers(event_bus: EventBus) -> None:
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            event_bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group="trader_memory",
            )
