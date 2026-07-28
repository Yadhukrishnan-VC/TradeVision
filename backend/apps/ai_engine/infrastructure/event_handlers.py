from __future__ import annotations

import logging
from collections.abc import Callable

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.ai_engine.infrastructure.ai_reasoning_orchestrator import (
    AIReasoningOrchestrator,
)

logger = logging.getLogger(__name__)

_orchestrator = AIReasoningOrchestrator()


def _handle_rule_fired(event: DomainEvent) -> None:
    _orchestrator.orchestrate(event)


SUBSCRIBED_EVENTS: dict[str, list[Callable[[DomainEvent], None]]] = {
    "rule_engine.RuleFired": [_handle_rule_fired],
}


def register_handlers(event_bus: EventBus) -> None:
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            event_bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group="ai_engine",
            )
    logger.debug("ai_engine_reasoning_handlers_registered")
