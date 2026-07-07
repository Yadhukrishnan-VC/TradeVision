"""
TradeVision AI — Redis-backed event bus.

Provides a thin publish/subscribe wrapper over Redis channels. All
application modules publish and subscribe through this interface, keeping
the Redis client details out of business logic.

Channel naming convention:
    analysis_event:{event_type}     — AnalysisEvent publications
    feed_status:{source_name}       — Data feed health updates
    system:{topic}                  — Operational / admin events

Usage::

    bus = EventBus.from_settings()

    # Publish
    bus.publish_analysis_event(event)

    # Subscribe (blocking — run in a dedicated thread or Celery worker)
    for event in bus.subscribe_analysis_events(EventType.PRICE_MOVEMENT):
        handle(event)
"""

import dataclasses
import json
import logging
import uuid
from collections.abc import Generator
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import redis as redis_lib

from core.events.event_types import AnalysisEvent, EventType
from core.exceptions import TradeVisionError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Channel name constants
# ---------------------------------------------------------------------------


class EventChannel:
    """Redis channel name constants."""

    ANALYSIS_EVENT_PREFIX: str = "analysis_event"
    FEED_STATUS_PREFIX: str = "feed_status"
    SYSTEM_PREFIX: str = "system"

    @staticmethod
    def for_event_type(event_type: EventType) -> str:
        """Return the channel name for a given EventType."""
        return f"{EventChannel.ANALYSIS_EVENT_PREFIX}:{event_type.value}"

    @staticmethod
    def for_feed(source_name: str) -> str:
        """Return the channel name for a data feed source."""
        return f"{EventChannel.FEED_STATUS_PREFIX}:{source_name}"

    @staticmethod
    def system(topic: str) -> str:
        """Return a system-level channel name."""
        return f"{EventChannel.SYSTEM_PREFIX}:{topic}"


# ---------------------------------------------------------------------------
# JSON serialisation
# ---------------------------------------------------------------------------


class _EventEncoder(json.JSONEncoder):
    """
    JSON encoder that handles types common in event payloads.

    Encodes Decimal as string (preserves precision), datetime as ISO-8601,
    UUID as hyphenated string, and Enum by value.
    """

    def default(self, obj: Any) -> Any:
        """Serialise types not supported by the standard JSON encoder."""
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, Enum):
            return obj.value
        return super().default(obj)


def _serialise_event(event: AnalysisEvent) -> str:
    """Serialise an AnalysisEvent to a JSON string for Redis publication."""
    return json.dumps(dataclasses.asdict(event), cls=_EventEncoder)


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class EventBusError(TradeVisionError):
    """Raised when an EventBus operation fails."""


class EventBus:
    """
    Redis pub/sub event bus.

    Args:
        redis_client: Injected Redis client. Dependency injection makes the
                      bus independently unit-testable with a FakeRedis or mock.

    Note:
        Publishers and subscribers should use separate Redis connections when
        possible; Redis pub/sub blocks the connection while subscribing.
    """

    def __init__(self, redis_client: redis_lib.Redis) -> None:  # type: ignore[type-arg]
        """Initialise with an injected Redis client."""
        self._redis = redis_client

    @classmethod
    def from_settings(cls) -> "EventBus":
        """
        Construct an EventBus using the REDIS_URL from Django settings.

        Call this at the service layer or in Celery tasks where Django
        settings are available.
        """
        from django.conf import settings

        client: redis_lib.Redis = redis_lib.from_url(  # type: ignore[type-arg]
            settings.REDIS_URL,
            decode_responses=True,
        )
        return cls(client)

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish_analysis_event(self, event: AnalysisEvent) -> int:
        """
        Publish an AnalysisEvent to the appropriate channel.

        The channel is determined by the event's ``event_type``::

            analysis_event:price_movement
            analysis_event:volume_spike
            ...

        Args:
            event: The event to publish.

        Returns:
            Number of subscribers that received the message.

        Raises:
            EventBusError: If the Redis publish fails.
        """
        channel = EventChannel.for_event_type(event.event_type)
        payload = _serialise_event(event)

        try:
            receiver_count: int = self._redis.publish(channel, payload)
            logger.debug(
                "event_published",
                extra={
                    "channel": channel,
                    "event_id": str(event.id),
                    "symbol": event.symbol,
                    "receivers": receiver_count,
                },
            )
            return receiver_count
        except redis_lib.RedisError as exc:
            logger.error(
                "event_publish_failed",
                extra={"channel": channel, "error": str(exc)},
            )
            raise EventBusError(f"Failed to publish event to channel '{channel}'") from exc

    def publish_raw(self, channel: str, payload: dict[str, Any]) -> int:
        """
        Publish an arbitrary JSON payload to a named channel.

        Use for non-AnalysisEvent messages (feed status, system alerts).

        Args:
            channel: Redis channel name (use EventChannel constants).
            payload: JSON-serialisable dict.

        Returns:
            Number of subscribers that received the message.
        """
        try:
            message = json.dumps(payload, cls=_EventEncoder)
            return self._redis.publish(channel, message)
        except redis_lib.RedisError as exc:
            raise EventBusError(f"Failed to publish to channel '{channel}'") from exc

    # ------------------------------------------------------------------
    # Subscribing
    # ------------------------------------------------------------------

    def subscribe_analysis_events(
        self,
        *event_types: EventType,
    ) -> Generator[dict[str, Any], None, None]:
        """
        Subscribe to one or more analysis event channels.

        This is a blocking generator intended for use in long-running
        Celery workers or management commands. Run in a dedicated thread.

        Args:
            event_types: One or more ``EventType`` values to subscribe to.
                         Subscribes to all analysis events if none are given.

        Yields:
            Raw decoded JSON dicts from the channel. Callers are responsible
            for reconstructing the typed ``AnalysisEvent`` from the dict.

        Example::

            bus = EventBus.from_settings()
            for raw in bus.subscribe_analysis_events(EventType.PRICE_MOVEMENT):
                # raw is a dict; deserialise as needed
                logger.info("received_event", extra={"symbol": raw["symbol"]})
        """
        if event_types:
            channels = [EventChannel.for_event_type(et) for et in event_types]
        else:
            channels = [f"{EventChannel.ANALYSIS_EVENT_PREFIX}:*"]

        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)

        try:
            if not event_types:
                # Pattern subscribe for all analysis events
                pubsub.psubscribe(*channels)
            else:
                pubsub.subscribe(*channels)

            logger.info(
                "event_bus_subscribed",
                extra={"channels": channels},
            )

            for message in pubsub.listen():
                if message and message.get("type") in ("message", "pmessage"):
                    raw_data = message.get("data", "{}")
                    try:
                        yield json.loads(raw_data)
                    except json.JSONDecodeError:
                        logger.warning(
                            "event_bus_malformed_message",
                            extra={"raw": str(raw_data)[:200]},
                        )
        except redis_lib.RedisError as exc:
            logger.error(
                "event_bus_subscription_error",
                extra={"error": str(exc)},
            )
            raise EventBusError("Event bus subscription failed") from exc
        finally:
            pubsub.close()
