from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.models import StoredEvent

logger = logging.getLogger(__name__)


class FakeEventBus(EventBus):
    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[Callable[[DomainEvent], None], str]]] = {}
        self._wildcard_handlers: list[tuple[Callable[[DomainEvent], None], str]] = []
        self._published_events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self._published_events.append(event)

        StoredEvent.objects.create(
            event_id=event.event_id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            payload=event.payload,
            version=event.version,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            mirrored_to_stream=True,
        )

        handlers = self._handlers.get(event.event_type, [])
        for handler, consumer_group in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Handler failed in FakeEventBus",
                    extra={
                        "event_type": event.event_type,
                        "handler": getattr(handler, "__name__", str(handler)),
                        "consumer_group": consumer_group,
                    },
                )

        for handler, consumer_group in self._wildcard_handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "Wildcard handler failed in FakeEventBus",
                    extra={
                        "event_type": event.event_type,
                        "handler": getattr(handler, "__name__", str(handler)),
                        "consumer_group": consumer_group,
                    },
                )

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[DomainEvent], None],
        *,
        consumer_group: str,
    ) -> None:
        if event_type == "*":
            self._wildcard_handlers.append((handler, consumer_group))
            return

        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append((handler, consumer_group))

    @property
    def published_events(self) -> list[DomainEvent]:
        return list(self._published_events)

    def clear(self) -> None:
        self._handlers.clear()
        self._wildcard_handlers.clear()
        self._published_events.clear()
