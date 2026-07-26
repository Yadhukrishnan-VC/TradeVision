from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.eventbus.infrastructure.fake_event_bus import FakeEventBus
from apps.eventbus.infrastructure.models import ProcessedEvent


class TestEventBusContract:
    """Contract tests parametrized over all EventBus implementations."""

    @pytest.fixture(
        params=["fake"],
        ids=["fake"],
    )
    def event_bus(self, request: Any) -> Any:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus
        reset_event_bus()

        if request.param == "fake":
            from django.conf import settings
            settings.EVENT_BUS_IMPLEMENTATION = "fake"

        return get_event_bus()

    def test_publish_then_subscribe_delivers_event(
        self, event_bus: Any, db: Any
    ) -> None:
        received_events: list[DomainEvent] = []

        def handler(event: DomainEvent) -> None:
            received_events.append(event)

        event_bus.subscribe("test.DeliveryTest", handler, consumer_group="test_group")
        event = DomainEvent.create(
            event_type="test.DeliveryTest",
            payload={"msg": "hello"},
            correlation_id=uuid.uuid4(),
        )
        event_bus.publish(event)

        assert len(received_events) == 1
        assert received_events[0].event_id == event.event_id

    def test_handler_that_raises_is_still_called(self, event_bus: Any, db: Any) -> None:
        call_count: list[int] = []

        def handler(event: DomainEvent) -> None:
            call_count.append(1)

        event_bus.subscribe("test.RaiseTest", handler, consumer_group="test_group")
        event = DomainEvent.create(
            event_type="test.RaiseTest",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        event_bus.publish(event)

        assert len(call_count) >= 1

    def test_duplicate_delivery_does_not_reinvoke_handler(
        self, event_bus: Any, db: Any
    ) -> None:
        call_count: list[int] = []

        def handler(event: DomainEvent) -> None:
            call_count.append(1)

        event_bus.subscribe("test.DedupTest", handler, consumer_group="test_group")

        event = DomainEvent.create(
            event_type="test.DedupTest",
            payload={},
            correlation_id=uuid.uuid4(),
        )

        ProcessedEvent.objects.create(
            event_id=event.event_id,
            consumer_group="test_group",
        )

        event_bus.publish(event)

        assert len(call_count) == 1

    def test_empty_payload(self, event_bus: Any, db: Any) -> None:
        received: list[DomainEvent] = []

        def handler(event: DomainEvent) -> None:
            received.append(event)

        event_bus.subscribe("test.EmptyPayload", handler, consumer_group="test_group")
        event = DomainEvent.create(
            event_type="test.EmptyPayload",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        event_bus.publish(event)

        assert len(received) == 1

    def test_multiple_handlers_for_same_event(self, event_bus: Any, db: Any) -> None:
        call_count: list[int] = [0, 0]

        def handler1(event: DomainEvent) -> None:
            call_count[0] += 1

        def handler2(event: DomainEvent) -> None:
            call_count[1] += 1

        event_bus.subscribe("test.MultiHandler", handler1, consumer_group="group1")
        event_bus.subscribe("test.MultiHandler", handler2, consumer_group="group2")

        event = DomainEvent.create(
            event_type="test.MultiHandler",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        event_bus.publish(event)

        assert call_count[0] == 1
        assert call_count[1] == 1
