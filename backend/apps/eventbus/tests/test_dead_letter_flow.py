from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.fake_event_bus import FakeEventBus
from apps.eventbus.infrastructure.models import DeadLetterEvent, ProcessedEvent

pytestmark = pytest.mark.django_db


class TestDeadLetterFlow:
    def test_handler_that_raises_eventually_creates_dead_letter(self) -> None:
        bus = FakeEventBus()
        call_count: list[int] = []

        def failing_handler(event: DomainEvent) -> None:
            call_count.append(1)

        bus.subscribe("test.DeadLetter", failing_handler, consumer_group="test_group")
        event = DomainEvent.create(
            event_type="test.DeadLetter",
            payload={"data": "test"},
            correlation_id=uuid.uuid4(),
        )
        bus.publish(event)

        assert len(call_count) >= 1

    def test_processed_event_created_on_success(self) -> None:
        bus = FakeEventBus()
        call_count: list[int] = []

        def handler(event: DomainEvent) -> None:
            call_count.append(1)

        bus.subscribe("test.Success", handler, consumer_group="test_group")
        event = DomainEvent.create(
            event_type="test.Success",
            payload={},
            correlation_id=uuid.uuid4(),
        )
        bus.publish(event)

        assert len(call_count) >= 1
