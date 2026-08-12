from __future__ import annotations

import importlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis_asyncio
from celery import shared_task
from django.conf import settings
from django.db import transaction

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.models import DeadLetterEvent, ProcessedEvent, StoredEvent

logger = logging.getLogger(__name__)

RETRY_BACKOFF_SCHEDULE = [1, 5, 30, 120, 600]  # 1s, 5s, 30s, 2m, 10m
MAX_RETRIES = 5

# EVENTBUS-RELIABILITY-1 — pending-entry reclaim tuning.
# A stream entry is reclaimed when it has been pending (idle) in a consumer
# group's Pending Entries List for this long without a terminal outcome. The
# default is deliberately generous relative to the 60s ``time_limit`` of
# ``dispatch_event_to_handler`` so a healthy handler has time to finish.
RECLAIM_MIN_IDLE_SECONDS = 120
# TTL for the per-stream/group reclaim lock; prevents two overlapping Beat
# ticks (or a Beat tick racing a manual admin run) from double-claiming.
RECLAIM_LOCK_TTL_SECONDS = 30


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": MAX_RETRIES},
    retry_backoff_max=600,
    max_retries=MAX_RETRIES,
    soft_time_limit=30,
    time_limit=60,
)
def dispatch_event_to_handler(
    self: Any,
    event_dict: dict[str, Any],
    handler_path: str,
    consumer_group: str,
    stream_key: str | None = None,
    entry_id: str | None = None,
) -> None:
    """Celery task that executes one event handler with idempotency.

    Checks ProcessedEvent dedup before execution. On final failure,
    creates a DeadLetterEvent row and publishes a system-level
    ``system.HandlerDeadLettered`` operational signal.

    When ``stream_key`` and ``entry_id`` are supplied (the Redis Streams
    consumer path), the stream entry is acknowledged via ``XACK`` *only*
    after a terminal outcome: either successful handler completion (after
    ``ProcessedEvent`` is created) or final failure (after the dead-letter
    row is created). Retryable failures are deliberately NOT acked, keeping
    the entry in the consumer group's Pending Entries List so it can be
    reclaimed if the worker dies. Callers that omit these arguments (e.g.
    ``FakeEventBus``-backed tests) keep the previous no-ack behaviour.

    Args:
        event_dict: Serialized domain event data.
        handler_path: Dotted path to the handler callable.
        consumer_group: Consumer group name for dedup.
        stream_key: Redis stream key to acknowledge on terminal outcome.
        entry_id: Redis stream entry id to acknowledge on terminal outcome.
    """
    event = _deserialize_event(event_dict)
    request_id = str(event.event_id)

    if ProcessedEvent.objects.filter(
        event_id=event.event_id,
        consumer_group=consumer_group,
    ).exists():
        logger.info(
            "Event already processed, skipping",
            extra={"event_id": request_id, "consumer_group": consumer_group},
        )
        _ack_entry(stream_key, consumer_group, entry_id)
        return

    try:
        module_path, func_name = handler_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        handler = getattr(module, func_name)

        handler(event)

        ProcessedEvent.objects.create(
            event_id=event.event_id,
            consumer_group=consumer_group,
        )
        logger.info(
            "Handler completed",
            extra={"event_id": request_id, "handler": handler_path},
        )
        _ack_entry(stream_key, consumer_group, entry_id)
    except Exception as exc:
        logger.warning(
            "Handler failed",
            extra={
                "event_id": request_id,
                "handler": handler_path,
                "retries": self.request.retries if hasattr(self, "request") else 0,
                "error": str(exc),
            },
        )

        if self.request.retries >= MAX_RETRIES - 1:
            attempts = self.request.retries + 1
            _create_dead_letter(event, consumer_group, str(exc), attempts)

            from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
            dead_letter_event = DomainEvent.create(
                event_type="system.HandlerDeadLettered",
                payload={
                    "original_event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "consumer_group": consumer_group,
                    "failure_reason": str(exc),
                    "attempts": attempts,
                },
                correlation_id=event.correlation_id,
                causation_id=event.event_id,
            )
            bus = get_event_bus()
            try:
                bus.publish(dead_letter_event)
            except Exception:
                logger.exception("Failed to publish DeadLettered event")

            _ack_entry(stream_key, consumer_group, entry_id)

        raise


def _deserialize_event(event_dict: dict[str, Any]) -> DomainEvent:
    """Reconstruct a DomainEvent from its serialized dictionary form."""
    return DomainEvent(
        event_id=__import__("uuid").UUID(event_dict["event_id"]),
        event_type=event_dict["event_type"],
        occurred_at=datetime.fromisoformat(event_dict["occurred_at"]),
        payload=json.loads(event_dict["payload"]) if isinstance(event_dict["payload"], str) else event_dict["payload"],
        version=int(event_dict["version"]),
        correlation_id=__import__("uuid").UUID(event_dict["correlation_id"]),
        causation_id=__import__("uuid").UUID(event_dict["causation_id"]) if event_dict.get("causation_id") else None,
    )


def _create_dead_letter(
    event: DomainEvent,
    consumer_group: str,
    failure_reason: str,
    attempts: int,
) -> None:
    """Create a DeadLetterEvent record for a permanently failed event."""
    DeadLetterEvent.objects.create(
        event_id=event.event_id,
        event_type=event.event_type,
        consumer_group=consumer_group,
        payload=event.payload,
        failure_reason=failure_reason,
        attempts=attempts,
    )


def _poll_and_dispatch(
    r: redis_asyncio.Redis,
    stream_key: str,
    handler_path: str,
    consumer_group: str,
) -> None:
    import asyncio
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(
                r.xreadgroup(
                    consumer_group,
                    f"consumer-{consumer_group}",
                    {stream_key: ">"},
                    count=10,
                    block=1000,
                )
            )
        finally:
            loop.close()

        if not results:
            return

        for stream_name, entries in results:
            for entry_id, data in entries:
                dispatch_event_to_handler.delay(
                    event_dict=data,
                    handler_path=handler_path,
                    consumer_group=consumer_group,
                    stream_key=stream_name,
                    entry_id=entry_id,
                )
    except Exception:
        logger.exception(
            "Error polling stream",
            extra={"stream": stream_key, "consumer_group": consumer_group},
        )


@shared_task(soft_time_limit=10, time_limit=15)
def poll_event_streams() -> None:
    """Celery beat task that polls Redis Streams for new events.

    Reads pending entries from all registered consumer groups and
    dispatches them to ``dispatch_event_to_handler``.
    """
    from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
    bus = get_event_bus()

    if not hasattr(bus, "_handlers") or not bus._handlers:
        return

    import asyncio
    r = redis_asyncio.from_url(settings.CELERY_BROKER_URL, decode_responses=True)

    for event_type, handler_list in bus._handlers.items():
        stream_key = f"events:{event_type}"
        for handler_path, consumer_group in handler_list:
            _poll_and_dispatch(r, stream_key, handler_path, consumer_group)

        wildcard_groups = getattr(bus, "wildcard_handlers", [])
        for handler_path, consumer_group in wildcard_groups:
            _poll_and_dispatch(r, stream_key, handler_path, consumer_group)


def _ack_event(r: redis_asyncio.Redis, stream: str, group: str, entry_id: str) -> None:
    """Acknowledge a stream entry as processed."""
    import asyncio
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(r.xack(stream, group, entry_id))
    finally:
        loop.close()


def _ack_entry(stream_key: str | None, consumer_group: str | None, entry_id: str | None) -> None:
    """Acknowledge a stream entry once its handler reached a terminal outcome.

    No-op when ``stream_key`` or ``entry_id`` is missing (FakeEventBus-style
    callers that have no stream/entry concept). Failures to ack are logged but
    not raised: an already-processed entry that stays in the Pending Entries
    List is a safe no-op for the reclaim sweep (which re-dispatches it and
    re-acks via the ``ProcessedEvent`` dedup check).
    """
    if not stream_key or not entry_id:
        return
    try:
        r = redis_asyncio.from_url(settings.CELERY_BROKER_URL, decode_responses=True)
        _ack_event(r, stream_key, consumer_group or "", entry_id)
    except Exception:
        logger.exception(
            "Failed to acknowledge stream entry after terminal outcome",
            extra={"stream": stream_key, "entry_id": entry_id},
        )


@shared_task(soft_time_limit=30, time_limit=60)
def reclaim_stale_pending_events(
    min_idle_seconds: int = RECLAIM_MIN_IDLE_SECONDS,
) -> None:
    """Reclaim stream entries left pending by crashed/killed consumers.

    For every registered ``(stream_key, consumer_group)`` pair, claims entries
    in the group's Pending Entries List that have been idle longer than
    ``min_idle_seconds`` via ``XAUTOCLAIM``, then re-dispatches each through
    ``dispatch_event_to_handler`` (already idempotent via the ``ProcessedEvent``
    check, so reclaiming an entry that actually completed right before a crash
    is a safe no-op followed by an ack).

    Entries whose delivery count (from the PEL's ``times_delivered``) has
    reached ``MAX_RETRIES`` are dead-lettered directly here and acked, rather
    than re-dispatched, keeping the PEL bounded. Each stream/group is guarded
    by a short-TTL Redis lock so overlapping Beat ticks cannot double-claim.
    """
    from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
    bus = get_event_bus()

    if not hasattr(bus, "_handlers") or not bus._handlers:
        return

    r = redis_asyncio.from_url(settings.CELERY_BROKER_URL, decode_responses=True)

    for event_type, handler_list in bus._handlers.items():
        stream_key = f"events:{event_type}"
        for handler_path, consumer_group in handler_list:
            _reclaim_stream(r, stream_key, handler_path, consumer_group, min_idle_seconds)

        wildcard_groups = getattr(bus, "wildcard_handlers", [])
        for handler_path, consumer_group in wildcard_groups:
            _reclaim_stream(r, stream_key, handler_path, consumer_group, min_idle_seconds)


def _reclaim_stream(
    r: redis_asyncio.Redis,
    stream_key: str,
    handler_path: str,
    consumer_group: str,
    min_idle_seconds: int,
) -> None:
    """Reclaim idle pending entries for one (stream, group) pair.

    Redis-only work (lock acquire/release, XAUTOCLAIM, delivery-count
    inspection) runs inside a dedicated event loop; re-dispatch and
    dead-lettering are performed synchronously afterwards so no Celery
    ``.delay()`` call or ORM write ever blocks a running loop.
    """
    import asyncio

    lock_key = f"eventbus:reclaim_lock:{stream_key}:{consumer_group}"
    claimed: list[tuple[str, dict[str, Any], int]] = []
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        acquired = loop.run_until_complete(
            r.set(lock_key, "1", nx=True, ex=RECLAIM_LOCK_TTL_SECONDS)
        )
        if not acquired:
            logger.info(
                "Reclaim lock already held, skipping",
                extra={"stream": stream_key, "consumer_group": consumer_group},
            )
            return

        try:
            claimed = loop.run_until_complete(
                _claim_idle_entries(r, stream_key, consumer_group, min_idle_seconds)
            )
        finally:
            loop.run_until_complete(r.delete(lock_key))
    finally:
        loop.close()

    for entry_id, data, delivery_count in claimed:
        if delivery_count >= MAX_RETRIES:
            logger.warning(
                "Dead-lettering pending event that exceeded max delivery attempts",
                extra={
                    "stream": stream_key,
                    "consumer_group": consumer_group,
                    "entry_id": entry_id,
                    "delivery_count": delivery_count,
                },
            )
            _dead_letter_claimed_entry(
                stream_key, consumer_group, entry_id, data, delivery_count
            )
        else:
            dispatch_event_to_handler.delay(
                event_dict=data,
                handler_path=handler_path,
                consumer_group=consumer_group,
                stream_key=stream_key,
                entry_id=entry_id,
            )


async def _claim_idle_entries(
    r: redis_asyncio.Redis,
    stream_key: str,
    consumer_group: str,
    min_idle_seconds: int,
) -> list[tuple[str, dict[str, Any], int]]:
    """XAUTOCLAIM idle entries, returning (entry_id, data, delivery_count)."""
    pending = await r.xpending(stream_key, consumer_group)
    if not pending or pending.get("pending", 0) == 0:
        return []

    consumer_name = f"reclaimer-{consumer_group}-{os.getpid()}"
    claimed: list[tuple[str, dict[str, Any], int]] = []
    next_id = "0-0"
    while True:
        result = await r.xautoclaim(
            stream_key,
            consumer_group,
            consumer_name,
            min_idle_time=min_idle_seconds * 1000,
            start_id=next_id,
            count=50,
        )
        next_id = result[0]
        claimed_entries = result[1]

        for entry_id, data in claimed_entries:
            delivery_count = await _delivery_count(
                r, stream_key, consumer_group, entry_id
            )
            claimed.append((entry_id, data, delivery_count))

        if not claimed_entries or next_id == "0-0":
            break

    return claimed


async def _delivery_count(
    r: redis_asyncio.Redis,
    stream_key: str,
    consumer_group: str,
    entry_id: str,
) -> int:
    """Return the PEL delivery count (``times_delivered``) for an entry."""
    detail = await r.xpending_range(stream_key, consumer_group, entry_id, entry_id, 1)
    if not detail:
        return MAX_RETRIES
    return int(detail[0].get("times_delivered", 0))


def _dead_letter_claimed_entry(
    stream_key: str,
    consumer_group: str,
    entry_id: str,
    data: dict[str, Any],
    delivery_count: int,
) -> None:
    """Dead-letter and ack a claimed entry that exceeded max delivery attempts.

    Runs in synchronous context: the ``DeadLetterEvent`` row is created and the
    ``system.HandlerDeadLettered`` signal published *before* the stream entry is
    acknowledged, so a crash between the two still leaves a durable record and a
    re-claimable PEL entry rather than a silently lost event.
    """
    from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

    event = _deserialize_event(data)

    if DeadLetterEvent.objects.filter(
        event_id=event.event_id,
        consumer_group=consumer_group,
    ).exists():
        # Already terminal — just close the PEL entry (idempotent reclaim).
        _ack_entry(stream_key, consumer_group, entry_id)
        return

    failure_reason = (
        f"Event delivery exceeded max attempts ({delivery_count} >= {MAX_RETRIES}) "
        "without a terminal outcome"
    )
    _create_dead_letter(event, consumer_group, failure_reason, delivery_count)

    dead_letter_event = DomainEvent.create(
        event_type="system.HandlerDeadLettered",
        payload={
            "original_event_id": str(event.event_id),
            "event_type": event.event_type,
            "consumer_group": consumer_group,
            "failure_reason": failure_reason,
            "attempts": delivery_count,
        },
        correlation_id=event.correlation_id,
        causation_id=event.event_id,
    )
    bus = get_event_bus()
    try:
        bus.publish(dead_letter_event)
    except Exception:
        logger.exception("Failed to publish DeadLettered event")

    _ack_entry(stream_key, consumer_group, entry_id)


@shared_task(soft_time_limit=30, time_limit=60)
def replay_unpublished_events() -> None:
    """Safety-net beat task that re-mirrors events not yet in Redis.

    Scans StoredEvent rows with ``mirrored_to_stream=False`` that
    are older than 30 seconds and retries the Redis mirror operation.
    """
    from datetime import timedelta
    from django.utils import timezone as django_timezone

    cutoff = django_timezone.now() - timedelta(seconds=30)
    unpublished = StoredEvent.objects.filter(
        mirrored_to_stream=False,
        occurred_at__lte=cutoff,
    )

    r = redis_asyncio.from_url(settings.CELERY_BROKER_URL, decode_responses=True)

    for stored in unpublished:
        try:
            stream_key = f"events:{stored.event_type}"
            data = {
                "event_id": str(stored.event_id),
                "event_type": stored.event_type,
                "occurred_at": stored.occurred_at.isoformat(),
                "payload": json.dumps(stored.payload, default=str),
                "version": str(stored.version),
                "correlation_id": str(stored.correlation_id),
                "causation_id": str(stored.causation_id) if stored.causation_id else "",
            }

            import asyncio
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                loop.run_until_complete(r.xadd(stream_key, data))
            finally:
                loop.close()

            stored.mirrored_to_stream = True
            stored.save(update_fields=["mirrored_to_stream"])

            logger.info(
                "Re-published unpublished event",
                extra={"event_id": str(stored.event_id), "event_type": stored.event_type},
            )
        except Exception as exc:
            logger.error(
                "Failed to re-publish event",
                extra={
                    "event_id": str(stored.event_id),
                    "event_type": stored.event_type,
                    "error": str(exc),
                },
            )
