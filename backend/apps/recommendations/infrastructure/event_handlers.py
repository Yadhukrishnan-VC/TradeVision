from __future__ import annotations

from collections.abc import Callable

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.recommendations.infrastructure.tasks import create_recommendation


def _handle_rule_fired(event: DomainEvent) -> None:
    payload = event.payload
    create_recommendation.delay(
        symbol=payload["symbol"],
        rule_id=payload["rule_id"],
        analysis_event_id=payload.get("analysis_event_id"),
        trigger_data=payload.get("trigger_data", {}),
        correlation_id=str(event.correlation_id),
    )


SUBSCRIBED_EVENTS: dict[str, list[Callable[[DomainEvent], None]]] = {
    "rule_engine.RuleFired": [_handle_rule_fired],
}


def register_handlers(event_bus: EventBus) -> None:
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            event_bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group="recommendations",
            )
