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
from apps.eventbus.domain.exceptions import EventBusError, EventPublishError
from apps.eventbus.infrastructure.models import StoredEvent

logger = logging.getLogger(__name__)


class _DomainEventEncoder(json.JSONEncoder):
    def default(self, o: Any) -> str:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Exception):
            return str(o)
        return super().default(o)


class RedisStreamsEventBus(EventBus):
    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[str, str]]] = {}
        self._wildcard_handlers: list[tuple[str, str]] = []
        self._redis: redis_asyncio.Redis | None = None

    def _get_redis(self) -> redis_asyncio.Redis:
        if self._redis is None:
            self._redis = redis_asyncio.from_url(
                settings.CELERY_BROKER_URL,
                decode_responses=True,
            )
        return self._redis

    def publish(self, event: DomainEvent) -> None:
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
                    "event_type": str(event.event_type),
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
        handler_path = f"{handler.__module__}.{handler.__name__}" if callable(handler) else str(handler)

        if event_type == "*":
            for existing_path, existing_group in self._wildcard_handlers:
                if existing_group != consumer_group:
                    continue
                if existing_path == handler_path:
                    return
                raise EventBusError(
                    f"Duplicate subscription for event_type={event_type!r} "
                    f"consumer_group={consumer_group!r} already bound to handler "
                    f"{existing_path!r}"
                )
            self._wildcard_handlers.append((handler_path, consumer_group))
            for et in self._handlers:
                self._ensure_consumer_group(et, consumer_group)
            return

        for existing_path, existing_group in self._handlers.get(event_type, []):
            if existing_group != consumer_group:
                continue
            if existing_path == handler_path:
                return
            raise EventBusError(
                f"Duplicate subscription for event_type={event_type!r} "
                f"consumer_group={consumer_group!r} already bound to handler "
                f"{existing_path!r}"
            )

        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append((handler_path, consumer_group))

        self._ensure_consumer_group(event_type, consumer_group)

    def _ensure_consumer_group(self, event_type: str, consumer_group: str) -> None:
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

    @property
    def wildcard_handlers(self) -> list[tuple[str, str]]:
        return list(self._wildcard_handlers)
