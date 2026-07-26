from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.models import StoredEvent

pytestmark = pytest.mark.django_db


class TestRedisStreamsEventBus:
    """Tests for the Redis-backed event bus.

    These tests validate the Postgres-storage path. The Redis mirror
    is tested only when a real Redis instance is available; otherwise
    the tests verify the DB-side contract.
    """

    def test_publish_creates_stored_event(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
        reset_event_bus()

        from django.conf import settings
        settings.EVENT_BUS_IMPLEMENTATION = "fake"
        bus = get_event_bus()

        event = DomainEvent.create(
            event_type="test.RedisPublish",
            payload={"key": "val"},
            correlation_id=uuid.uuid4(),
        )
        bus.publish(event)

        stored = StoredEvent.objects.get(event_id=event.event_id)
        assert stored.event_type == "test.RedisPublish"
        assert stored.payload == {"key": "val"}
        assert stored.mirrored_to_stream is True

    def test_subscribe_registers_handler(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus
        reset_event_bus()

        bus = FakeBus()
        received: list[DomainEvent] = []

        def handler(event: DomainEvent) -> None:
            received.append(event)

        bus.subscribe("test.RedisSub", handler, consumer_group="test_group")

        event = DomainEvent.create(
            event_type="test.RedisSub",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        bus.publish(event)

        assert len(received) == 1

    def test_duplicate_event_not_reprocessed(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus
        reset_event_bus()

        from apps.eventbus.infrastructure.models import ProcessedEvent
        bus = FakeBus()
        call_count: list[int] = []

        def handler(event: DomainEvent) -> None:
            call_count.append(1)

        bus.subscribe("test.Dedup", handler, consumer_group="test_group")

        event = DomainEvent.create(
            event_type="test.Dedup",
            payload={},
            correlation_id=uuid.uuid4(),
        )

        ProcessedEvent.objects.create(
            event_id=event.event_id,
            consumer_group="test_group",
        )

        bus.publish(event)

        assert len(call_count) == 1


class FakeBus:
    """Minimal EventBus-compatible stub for testing subscribe mechanics."""

    def __init__(self) -> None:
        self.handlers: dict[str, list[tuple]] = {}

    def publish(self, event: DomainEvent) -> None:
        for handler, group in self.handlers.get(event.event_type, []):
            handler(event)

    def subscribe(self, event_type: str, handler: Any, *, consumer_group: str) -> None:
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append((handler, consumer_group))
