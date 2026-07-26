from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from apps.eventbus.domain.events import DomainEvent


@runtime_checkable
class EventBus(Protocol):
    """Abstract interface for the event bus.

    Every component that publishes or subscribes to domain events
    depends on this protocol rather than on a concrete implementation.
    This enables swapping between the production Redis-backed bus
    and the in-memory FakeEventBus for testing.
    """

    def publish(self, event: DomainEvent) -> None:
        """Publish a domain event to all registered subscribers.

        Args:
            event: The domain event to publish.

        Raises:
            EventPublishError: If the underlying transport fails.
        """
        ...

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[DomainEvent], None],
        *,
        consumer_group: str,
    ) -> None:
        """Register a handler for the given event type.

        Args:
            event_type: The event type string to subscribe to.
            handler: The callable that will process the event.
            consumer_group: The consumer group name for this handler.
        """
        ...
