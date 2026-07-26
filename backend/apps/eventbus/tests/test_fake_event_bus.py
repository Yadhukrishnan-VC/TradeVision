from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.fake_event_bus import FakeEventBus
from apps.eventbus.infrastructure.models import StoredEvent


@pytest.mark.django_db
class TestFakeEventBus:
    def test_publish_stores_event_in_db(self) -> None:
        bus = FakeEventBus()
        event = DomainEvent.create(
            event_type="test.Stored",
            payload={"data": 1},
            correlation_id=uuid.uuid4(),
        )
        bus.publish(event)

        assert StoredEvent.objects.filter(event_id=event.event_id).exists()

    def test_published_events_tracking(self) -> None:
        bus = FakeEventBus()
        event = DomainEvent.create(
            event_type="test.Tracked",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        bus.publish(event)

        assert len(bus.published_events) == 1
        assert bus.published_events[0].event_id == event.event_id

    def test_clear_resets_state(self) -> None:
        bus = FakeEventBus()
        event = DomainEvent.create(
            event_type="test.ClearTest",
            payload={},
            correlation_id=uuid.uuid4(),
        )

        def handler(event: DomainEvent) -> None:
            pass

        bus.subscribe("test.ClearTest", handler, consumer_group="g")
        bus.publish(event)
        assert len(bus.published_events) == 1

        bus.clear()
        assert len(bus.published_events) == 0

    def test_handlers_called_in_order(self) -> None:
        bus = FakeEventBus()
        order: list[str] = []

        def handler_a(event: DomainEvent) -> None:
            order.append("a")

        def handler_b(event: DomainEvent) -> None:
            order.append("b")

        bus.subscribe("test.Order", handler_a, consumer_group="g1")
        bus.subscribe("test.Order", handler_b, consumer_group="g2")

        event = DomainEvent.create(
            event_type="test.Order",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        bus.publish(event)

        assert order == ["a", "b"]
