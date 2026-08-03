from __future__ import annotations

import uuid

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.domain.exceptions import EventBusError
from apps.eventbus.infrastructure.fake_event_bus import FakeEventBus
from apps.eventbus.infrastructure.redis_event_bus import RedisStreamsEventBus


def _dummy_handler(event: DomainEvent) -> None:
    pass


@pytest.mark.django_db
class TestSubscribeDedupFakeBus:
    """FakeEventBus.subscribe() must be idempotent and reject conflicts."""

    def test_duplicate_subscription_stores_handler_once(self) -> None:
        bus = FakeEventBus()
        bus.subscribe("test.Dup", _dummy_handler, consumer_group="test_group")
        bus.subscribe("test.Dup", _dummy_handler, consumer_group="test_group")
        bus.subscribe("test.Dup", _dummy_handler, consumer_group="test_group")

        assert len(bus.handlers["test.Dup"]) == 1

    def test_duplicate_subscription_fires_handler_once(self) -> None:
        bus = FakeEventBus()
        calls: list[int] = []

        def handler(event: DomainEvent) -> None:
            calls.append(1)

        bus.subscribe("test.FireOnce", handler, consumer_group="test_group")
        bus.subscribe("test.FireOnce", handler, consumer_group="test_group")

        bus.publish(
            DomainEvent.create(
                event_type="test.FireOnce",
                payload={},
                correlation_id=uuid.uuid4(),
            )
        )

        assert len(calls) == 1

    def test_different_handler_same_group_raises(self) -> None:
        bus = FakeEventBus()
        bus.subscribe("test.Conflict", _dummy_handler, consumer_group="test_group")

        def other_handler(event: DomainEvent) -> None:
            pass

        with pytest.raises(EventBusError):
            bus.subscribe("test.Conflict", other_handler, consumer_group="test_group")

        # The conflicting handler is not silently appended.
        assert len(bus.handlers["test.Conflict"]) == 1

    def test_same_handler_different_group_is_kept(self) -> None:
        bus = FakeEventBus()
        bus.subscribe("test.MultiGroup", _dummy_handler, consumer_group="group_a")
        bus.subscribe("test.MultiGroup", _dummy_handler, consumer_group="group_b")

        assert len(bus.handlers["test.MultiGroup"]) == 2


@pytest.mark.django_db
class TestSubscribeDedupRedisBus:
    """RedisStreamsEventBus.subscribe() must be idempotent and reject conflicts."""

    def test_duplicate_subscription_stores_handler_once(self) -> None:
        bus = RedisStreamsEventBus()
        bus.subscribe("test.Dup", _dummy_handler, consumer_group="test_group")
        bus.subscribe("test.Dup", _dummy_handler, consumer_group="test_group")

        assert len(bus.handlers["test.Dup"]) == 1

    def test_different_handler_same_group_raises(self) -> None:
        bus = RedisStreamsEventBus()
        bus.subscribe("test.Conflict", _dummy_handler, consumer_group="test_group")

        def other_handler(event: DomainEvent) -> None:
            pass

        with pytest.raises(EventBusError):
            bus.subscribe("test.Conflict", other_handler, consumer_group="test_group")

        assert len(bus.handlers["test.Conflict"]) == 1
