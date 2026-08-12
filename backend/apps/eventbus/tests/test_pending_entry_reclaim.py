from __future__ import annotations

import uuid
from typing import Any

import pytest
import redis as redis_lib

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.models import ProcessedEvent

pytestmark = pytest.mark.django_db


def recording_handler(event: DomainEvent) -> None:
    """Handler that records invocations via the module call registry.

    Uses a function attribute to carry the list reference, avoiding
    pytest's dual-import module duplication issues.
    """
    recording_handler._CALLS.append(str(event.event_id))


_CALLS: list[str] = []


# Attach the list to the handler function so it can access it without
# relying on module imports (which pytest may duplicate).
recording_handler._CALLS = _CALLS


@pytest.fixture(autouse=True)
def _clear_calls() -> None:
    _CALLS.clear()


def _serialize(event: DomainEvent) -> dict[str, str]:
    return {
        "event_id": str(event.event_id),
        "event_type": event.event_type,
        "occurred_at": event.occurred_at.isoformat(),
        "payload": event.payload,
        "version": str(event.version),
        "correlation_id": str(event.correlation_id),
        "causation_id": "",
    }


class TestPendingEntryReclaim:
    """Reclaim sweep must recover entries orphaned by a crashed consumer."""

    def _publish_and_claim_without_dispatch(
        self,
        redis_client: redis_lib.Redis,
        *,
        event_type: str,
        consumer_group: str,
    ) -> tuple[str, str, DomainEvent]:
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
                payload={"key": "reclaim"},
                correlation_id=uuid.uuid4(),
            )
            bus.subscribe(event_type, recording_handler, consumer_group=consumer_group)
            bus.publish(event)

        stream_key = f"events:{event_type}"
        # Claim into the consumer group's Pending Entries List exactly like
        # _poll_and_dispatch would, then crash: no dispatch, no ack.
        claimed = redis_client.xreadgroup(
            consumer_group,
            "crashed-consumer",
            {stream_key: ">"},
            count=10,
            block=1,
        )
        assert claimed, "entry should be available to the consumer group"
        entry_id = claimed[0][1][0][0]
        return stream_key, entry_id, event

    def test_crashed_entry_reclaimed_and_processed_exactly_once(
        self, clean_redis: redis_lib.Redis
    ) -> None:
        """A claimed-but-under-processed entry is recovered by the sweep.

        The event must be dispatched exactly once and the PEL emptied.
        """
        from django.test import override_settings

        from apps.eventbus.infrastructure.tasks import reclaim_stale_pending_events

        event_type = f"test.Reclaim.{uuid.uuid4().hex[:8]}"
        consumer_group = "grp_reclaim"
        stream_key, entry_id, event = self._publish_and_claim_without_dispatch(
            clean_redis,
            event_type=event_type,
            consumer_group=consumer_group,
        )

        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 1

        with override_settings(EVENT_BUS_IMPLEMENTATION="redis"):
            reclaim_stale_pending_events.run(min_idle_seconds=0)

        assert _CALLS == [str(event.event_id)]
        assert ProcessedEvent.objects.filter(
            event_id=event.event_id, consumer_group=consumer_group
        ).exists()
        # Reclaim + successful dispatch must empty the PEL.
        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 0

    def test_idempotent_reclaim_no_duplicate_execution(
        self, clean_redis: redis_lib.Redis
    ) -> None:
        """Reclaiming an already-processed entry must not re-run the handler."""
        from django.test import override_settings

        from apps.eventbus.infrastructure.tasks import reclaim_stale_pending_events

        event_type = f"test.ReclaimIdem.{uuid.uuid4().hex[:8]}"
        consumer_group = "grp_reclaim_idem"
        stream_key, entry_id, event = self._publish_and_claim_without_dispatch(
            clean_redis,
            event_type=event_type,
            consumer_group=consumer_group,
        )

        # Event actually completed right before the crash → ProcessedEvent exists
        # but the PEL entry sits un-acked.
        ProcessedEvent.objects.create(
            event_id=event.event_id, consumer_group=consumer_group
        )
        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 1

        with override_settings(EVENT_BUS_IMPLEMENTATION="redis"):
            reclaim_stale_pending_events.run(min_idle_seconds=0)

        assert _CALLS == []
        assert (
            ProcessedEvent.objects.filter(
                event_id=event.event_id, consumer_group=consumer_group
            ).count()
            == 1
        )
        # Safe no-op re-ack closes the PEL entry.
        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 0

    def test_overlapping_sweeps_do_not_double_claim(
        self, clean_redis: redis_lib.Redis
    ) -> None:
        """Holding the reclaim lock must make a concurrent sweep a no-op."""
        from django.test import override_settings

        from apps.eventbus.infrastructure.tasks import reclaim_stale_pending_events

        event_type = f"test.ReclaimLock.{uuid.uuid4().hex[:8]}"
        consumer_group = "grp_reclaim_lock"
        stream_key, entry_id, event = self._publish_and_claim_without_dispatch(
            clean_redis,
            event_type=event_type,
            consumer_group=consumer_group,
        )

        lock_key = f"eventbus:reclaim_lock:{stream_key}:{consumer_group}"
        clean_redis.set(lock_key, "1", nx=True)

        with override_settings(EVENT_BUS_IMPLEMENTATION="redis"):
            reclaim_stale_pending_events.run(min_idle_seconds=0)

        # Sweep skipped the stream entirely: entry not dispatched, still pending.
        assert _CALLS == []
        assert clean_redis.xpending(stream_key, consumer_group)["pending"] == 1


RECLAIM_TASK = "apps.eventbus.infrastructure.tasks.reclaim_stale_pending_events"


def test_reclaim_task_registered_in_beat_schedule() -> None:
    from django.conf import settings

    assert RECLAIM_TASK in {
        entry["task"] for entry in settings.CELERY_BEAT_SCHEDULE.values()
    }
    entry = next(
        e for e in settings.CELERY_BEAT_SCHEDULE.values() if e["task"] == RECLAIM_TASK
    )
    assert entry["options"]["queue"] == "maintenance"