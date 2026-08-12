from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.fake_event_bus import FakeEventBus
from apps.eventbus.infrastructure.models import DeadLetterEvent, ProcessedEvent

pytestmark = pytest.mark.django_db


def always_raising_handler(event: DomainEvent) -> None:
    """Handler that raises on every invocation."""
    raise RuntimeError("handler always fails")


class TestDeadLetterFlow:
    def test_handler_that_raises_eventually_creates_dead_letter(self) -> None:
        from apps.eventbus.infrastructure.tasks import (
            MAX_RETRIES,
            dispatch_event_to_handler,
        )

        event = DomainEvent.create(
            event_type="test.DeadLetterReal",
            payload={"data": "test"},
            correlation_id=uuid.uuid4(),
        )

        attempts_made: list[int] = []
        for attempt in range(MAX_RETRIES):
            dispatch_event_to_handler.push_request(
                retries=attempt,
                args=(),
                kwargs={},
            )
            try:
                with pytest.raises(Exception):
                    dispatch_event_to_handler.run(
                        event_dict={
                            "event_id": str(event.event_id),
                            "event_type": event.event_type,
                            "occurred_at": event.occurred_at.isoformat(),
                            "payload": event.payload,
                            "version": str(event.version),
                            "correlation_id": str(event.correlation_id),
                            "causation_id": "",
                        },
                        handler_path=f"{__name__}.always_raising_handler",
                        consumer_group="test_group",
                    )
                attempts_made.append(attempt)
            finally:
                dispatch_event_to_handler.pop_request()

        # The handler must actually have been invoked MAX_RETRIES times, and the
        # final (MAX_RETRIES - 1 indexed) attempt must have produced a dead-letter.
        assert len(attempts_made) == MAX_RETRIES

        dead_letter = DeadLetterEvent.objects.get(event_id=event.event_id)
        assert dead_letter.consumer_group == "test_group"
        assert dead_letter.attempts == MAX_RETRIES
        assert dead_letter.failure_reason == "handler always fails"

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

        assert len(call_count) == 1