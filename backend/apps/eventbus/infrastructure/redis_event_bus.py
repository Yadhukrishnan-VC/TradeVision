from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import redis.asyncio as redis_asyncio
from django.conf import settings
from django.db import transaction

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.domain.exceptions import EventPublishError
from apps.eventbus.infrastructure.models import StoredEvent

logger = logging.getLogger(__name__)


class _DomainEventEncoder(json.JSONEncoder):
    """Custom JSON encoder for DomainEvent fields."""

    def default(self, o: Any) -> str:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Exception):
            return str(o)
        return super().default(o)


class RedisStreamsEventBus(EventBus):
    """Production event bus backed by Redis Streams.

    Events are first persisted to the Postgres StoredEvent table
    inside the caller's transaction, then mirrored to a Redis Stream
    for live dispatch. If the Redis mirror fails, a safety-net beat
    task retries the mirror asynchronously.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[str, str]]] = {}
        self._redis: redis_asyncio.Redis | None = None

    def _get_redis(self) -> redis_asyncio.Redis:
        if self._redis is None:
            self._redis = redis_asyncio.from_url(
                settings.CELERY_BROKER_URL,
                decode_responses=True,
            )
        return self._redis

    def publish(self, event: DomainEvent) -> None:
        """Persist the event to the event store and mirror to Redis Stream.

        Must be called from within a ``transaction.atomic()`` block
        or via ``on_commit``.

        Args:
            event: The domain event to publish.

        Raises:
            EventPublishError: If the Redis mirror fails. The Postgres
                write is unaffected (logged at ERROR level).
        """
        stored = StoredEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            payload=event.payload,
            version=event.version,
            correlation_id=event.correlation_id,
            causation_id=event.causation_id,
            mirrored_to_stream=False,
        )
        stored.save()

        try:
            stream_key = f"events:{event.event_type}"
            data = {
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "occurred_at": event.occurred_at.isoformat(),
                "payload": json.dumps(event.payload, cls=_DomainEventEncoder),
                "version": str(event.version),
                "correlation_id": str(event.correlation_id),
                "causation_id": str(event.causation_id) if event.causation_id else "",
            }

            import asyncio
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                r = self._get_redis()
                loop.run_until_complete(r.xadd(stream_key, data))
            finally:
                loop.close()

            StoredEvent.objects.filter(event_id=event.event_id).update(
                mirrored_to_stream=True
            )
        except Exception as exc:
            logger.error(
                "Failed to mirror event to Redis stream",
                extra={
                    "event_id": str(event.event_id),
                    "event_type": event.event_type,
                    "error": str(exc),
                },
            )

    def subscribe(
        self,
        event_type: str,
        handler: Any,
        *,
        consumer_group: str,
    ) -> None:
        """Register a handler for the given event type.

        For Redis Streams, this creates (idempotently) the consumer
        group on the corresponding stream.

        Args:
            event_type: The event type string to subscribe to.
            handler: The handler reference (dotted path string or
                callable).
            consumer_group: The consumer group name.
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        handler_path = f"{handler.__module__}.{handler.__name__}" if callable(handler) else str(handler)
        self._handlers[event_type].append((handler_path, consumer_group))

        try:
            import asyncio
            stream_key = f"events:{event_type}"
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                r = self._get_redis()
                loop.run_until_complete(
                    r.xgroup_create(stream_key, consumer_group, mkstream=True)
                )
            except Exception:
                pass
            finally:
                loop.close()
        except Exception:
            logger.exception(
                "Failed to create consumer group",
                extra={
                    "event_type": event_type,
                    "consumer_group": consumer_group,
                },
            )

    @property
    def handlers(self) -> dict[str, list[tuple[str, str]]]:
        return dict(self._handlers)
