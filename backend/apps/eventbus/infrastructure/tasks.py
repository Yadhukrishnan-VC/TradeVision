from __future__ import annotations

import importlib
import json
import logging
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
) -> None:
    """Celery task that executes one event handler with idempotency.

    Checks ProcessedEvent dedup before execution. On final failure,
    creates a DeadLetterEvent row and publishes a system-level
    ``system.HandlerDeadLettered`` operational signal.

    Args:
        event_dict: Serialized domain event data.
        handler_path: Dotted path to the handler callable.
        consumer_group: Consumer group name for dedup.
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
            _create_dead_letter(event, consumer_group, str(exc), self.request.retries + 1)

            from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
            dead_letter_event = DomainEvent.create(
                event_type="system.HandlerDeadLettered",
                payload={
                    "original_event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "consumer_group": consumer_group,
                    "failure_reason": str(exc),
                    "attempts": self.request.retries + 1,
                },
                correlation_id=event.correlation_id,
                causation_id=event.event_id,
            )
            bus = get_event_bus()
            try:
                bus.publish(dead_letter_event)
            except Exception:
                logger.exception("Failed to publish DeadLettered event")

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
                )
                _ack_event(r, stream_name, consumer_group, entry_id)
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
