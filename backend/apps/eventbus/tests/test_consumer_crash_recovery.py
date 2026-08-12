from __future__ import annotations

import uuid
from typing import Any

import pytest
import redis as redis_lib

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.models import ProcessedEvent

pytestmark = pytest.mark.django_db


def recording_handler(event: DomainEvent) -> None:
    """Handler that records invocations via the module call registry."""
    from apps.eventbus.tests.test_consumer_crash_recovery import _CALLS

    _CALLS.append(str(event.event_id))


_CALLS: list[str] = []


@pytest.fixture(autouse=True)
def _clear_calls() -> None:
    _CALLS.clear()


class TestConsumerCrashRecovery:
    """Stream entries must only be acknowledged after a terminal outcome."""

    def _publish_and_claim(
        self,
        redis_client: redis_lib.Redis,
        *,
        event_type: str,
        consumer_group: str,
    ) -> tuple[str, str, DomainEvent, dict[str, str]]:
        from django.test import override_settings

        from apps.eventbus.infrastructure.event_bus_factory import (
            get_event_bus,
            reset_event_bus,
        )

        with override_settings(EVENT_BUS_IMPLEMENTATION="redis"):
            reset_event_bus()
            bus = get_event_bus()
            event = DomainEvent.create(
                event_type=event_type,
                payload={"key": "recovery"},
                correlation_id=uuid.uuid4(),
            )
            bus.subscribe(event_type, recording_handler, consumer_group=consumer_group)
            bus.publish(event)

        stream_key = f"events:{event_type}"
        # Simulate the poll task having claimed the entry into the group's
        # Pending Entries List, exactly as _poll_and_dispatch does.
        claimed = redis_client.xreadgroup(
            consumer_group,
            "crashed-consumer",
            {stream_key: ">"},
            count=10,
            block=1,
        )
        assert claimed, "entry should be available to the consumer group"
        entry_id = claimed[0][1][0][0]
        data = claimed[0][1][0][1]
        return stream_key, entry_id, event, data

    def test_retryable_failure_not_acked_then_terminal_acks_and_dead_letters(
        self, clean_redis: redis_lib.Redis
    ) -> None:
        """A retryable failure keeps the PEL entry; only the terminal dead-letter acks.

        XPENDING length is asserted at every stage, not existence.
        """
        from apps.eventbus.infrastructure.models import DeadLetterEvent
        from apps.eventbus.infrastructure.tasks import (
            MAX_RETRIES,
            dispatch_event_to_handler,
        )

        event_type = f"test.CrashRecovery.{uuid.uuid4().hex[:8]}"
        consumer_group = "grp_crash_recovery"
        stream_key, entry_id, event, data = self._publish_and_claim(
            clean_redis,
            event_type=event_type,
            consumer_group=consumer_group,
        )
        raising_handler = (
            "apps.eventbus.tests.test_dead_letter_flow.always_raising_handler"
        )

        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 1

        # Retryable attempts (retries 0..MAX_RETRIES-2): body raises, NO ack.
        for attempt in range(MAX_RETRIES - 1):
            dispatch_event_to_handler.push_request(retries=attempt, args=(), kwargs={})
            try:
                with pytest.raises(RuntimeError):
                    dispatch_event_to_handler.run(
                        event_dict=data,
                        handler_path=raising_handler,
                        consumer_group=consumer_group,
                        stream_key=stream_key,
                        entry_id=entry_id,
                    )
            finally:
                dispatch_event_to_handler.pop_request()
            # Still pending — a retryable failure must not be acknowledged.
            assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 1
            assert not DeadLetterEvent.objects.filter(
                event_id=event.event_id, consumer_group=consumer_group
            ).exists()

        # Final attempt (retries == MAX_RETRIES - 1): dead-letter + ack.
        with pytest.raises(RuntimeError):
            dispatch_event_to_handler.push_request(
                retries=MAX_RETRIES - 1, args=(), kwargs={}
            )
            try:
                dispatch_event_to_handler.run(
                    event_dict=data,
                    handler_path=raising_handler,
                    consumer_group=consumer_group,
                    stream_key=stream_key,
                    entry_id=entry_id,
                )
            finally:
                dispatch_event_to_handler.pop_request()

        dead_letter = DeadLetterEvent.objects.get(
            event_id=event.event_id, consumer_group=consumer_group
        )
        assert dead_letter.attempts == MAX_RETRIES
        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 0

    def test_success_acks_immediately_after_processed_event(
        self, clean_redis: redis_lib.Redis
    ) -> None:
        """A successful handler acks the entry; PEL length drops to zero immediately."""
        from apps.eventbus.infrastructure.tasks import dispatch_event_to_handler

        event_type = f"test.CrashOk.{uuid.uuid4().hex[:8]}"
        consumer_group = "grp_crash_ok"
        stream_key, entry_id, event, data = self._publish_and_claim(
            clean_redis,
            event_type=event_type,
            consumer_group=consumer_group,
        )

        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 1

        self._run_task(
            dispatch_event_to_handler,
            event_dict=data,
            handler_path=(
                "apps.eventbus.tests.test_consumer_crash_recovery.recording_handler"
            ),
            consumer_group=consumer_group,
            stream_key=stream_key,
            entry_id=entry_id,
        )

        assert ProcessedEvent.objects.filter(
            event_id=event.event_id, consumer_group=consumer_group
        ).exists()
        # Exact PEL-length assertion: acked exactly once.
        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 0

    def test_duplicate_delivery_not_reprocessed_but_acked(self, clean_redis: redis_lib.Redis) -> None:
        """A reclaim of an already-processed entry must not re-run the handler."""
        from apps.eventbus.infrastructure.tasks import dispatch_event_to_handler

        event_type = f"test.CrashDedup.{uuid.uuid4().hex[:8]}"
        consumer_group = "grp_crash_dedup"
        stream_key, entry_id, event, data = self._publish_and_claim(
            clean_redis,
            event_type=event_type,
            consumer_group=consumer_group,
        )

        # Simulate "finished right before the crash": ProcessedEvent exists,
        # but the PEL entry was never acked.
        ProcessedEvent.objects.create(
            event_id=event.event_id, consumer_group=consumer_group
        )
        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 1

        self._run_task(
            dispatch_event_to_handler,
            event_dict=data,
            handler_path=(
                "apps.eventbus.tests.test_consumer_crash_recovery.recording_handler"
            ),
            consumer_group=consumer_group,
            stream_key=stream_key,
            entry_id=entry_id,
        )

        # No duplicate execution, entry acked (safe no-op re-ack).
        assert _CALLS == []
        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 0

    def _run_task(self, task: Any, **kwargs: Any) -> None:
        task.push_request(retries=0, args=(), kwargs={})
        try:
            task.run(**kwargs)
        finally:
            task.pop_request()