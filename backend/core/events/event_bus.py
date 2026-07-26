"""
TradeVision AI — Redis Streams-backed event bus.

Provides at-least-once publication and consumer-group-aware subscription for
``AnalysisEvent`` messages using Redis Streams. The notifications / WebSocket
fan-out path (Django Channels) remains on Redis Pub/Sub — see ADR-013.

Stream naming convention:
    analysis_event:{event_type}     — AnalysisEvent publications (Redis Stream)
    feed_status:{source_name}       — Data feed health updates (Redis Stream)
    system:{topic}                  — Operational / admin events (Redis Stream)

Usage::

    bus = EventBus.from_settings()

    # Publish
    entry_id = bus.publish_analysis_event(event)

    # Subscribe (blocking — run in a dedicated thread or Celery worker)
    for msg in bus.subscribe_analysis_events(
        EventType.PRICE_MOVEMENT,
        consumer_group="rule-engine",
        consumer_name="worker-1",
    ):
        handle(msg.data)
        bus.ack_event(msg.stream, "rule-engine", msg.entry_id)

Delivery guarantees:
    At-least-once. Consumers MUST call ``ack_event`` after successful
    processing. Unacknowledged messages remain pending in the consumer
    group and are redelivered on idle timeout or via ``XAUTOCLAIM``.

Consumer recovery:
    If a consumer crashes without acking, its pending messages can be
    claimed by another consumer in the same group::

        # Recovery worker — run on startup or periodically
        pending = redis.xpending(stream, group)
        if pending["pending"] > 0:
            claimed = redis.xautoclaim(stream, group, new_consumer,
                                       min_idle_time=30000)  # 30s idle

    See ``test_unacked_message_claimable_by_another_consumer`` in
    ``core/tests/test_event_bus.py`` for a working example.

Idempotency:
    At-least-once delivery means duplicate processing is possible.
    Every ``AnalysisEvent`` carries a UUID ``id`` field. Consumers
    should track processed event IDs (via a Redis set, a database
    ``processed_events`` table, or an in-memory bloom filter) and
    skip events whose ID has already been processed. The idempotency
    implementation is a per-consumer concern and should be added
    in the consumer's initialization code rather than in this module.

Backpressure & retention:
    Streams are bounded by ``MAXLEN ~ N`` approximate trimming on every
    ``XADD`` (N = ``settings.EVENT_STREAM_MAXLEN``, default 10000).
    If consumers fall behind, older messages are discarded — this is
    intentional because AnalysisEvents are time-sensitive; stale events
    should not be processed. Monitor stream length and pending count
    via Prometheus metrics (``EVENT_STREAM_LENGTH``,
    ``EVENT_STREAM_PENDING_TOTAL``) to detect consumer lag.
"""

import dataclasses
import json
import logging
import uuid
from collections.abc import Generator
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, NamedTuple

import redis as redis_lib

from core.events.event_types import AnalysisEvent, EventType
from core.exceptions import TradeVisionError
from core.metrics import (
    EVENT_CONSUMED_TOTAL,
    EVENT_PUBLISHED_TOTAL,
    EVENT_STREAM_LENGTH,
    EVENT_STREAM_PENDING_TOTAL,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stream name constants
# ---------------------------------------------------------------------------


class EventChannel:
    """Redis stream name constants."""

    ANALYSIS_EVENT_PREFIX: str = "analysis_event"
    FEED_STATUS_PREFIX: str = "feed_status"
    SYSTEM_PREFIX: str = "system"

    @staticmethod
    def for_event_type(event_type: EventType) -> str:
        """Return the stream key for a given EventType."""
        return f"{EventChannel.ANALYSIS_EVENT_PREFIX}:{event_type.value}"

    @staticmethod
    def for_feed(source_name: str) -> str:
        """Return the stream key for a data feed source."""
        return f"{EventChannel.FEED_STATUS_PREFIX}:{source_name}"

    @staticmethod
    def system(topic: str) -> str:
        """Return a system-level stream key."""
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
    """Serialise an AnalysisEvent to a JSON string for Redis stream publication."""
    return json.dumps(dataclasses.asdict(event), cls=_EventEncoder)


# ---------------------------------------------------------------------------
# Stream message container
# ---------------------------------------------------------------------------


class StreamMessage(NamedTuple):
    """A message received from a Redis stream, with stream/entry_id for ack."""

    stream: str
    entry_id: str
    data: dict


# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------


class EventBusError(TradeVisionError):
    """Raised when an EventBus operation fails."""


class EventBus:
    """
    Redis Streams-backed event bus.

    Uses Redis Streams with consumer groups for at-least-once delivery of
    ``AnalysisEvent`` messages. Every consumer MUST call ``ack_event`` after
    successfully processing a message, or it will be redelivered.

    Args:
        redis_client: Injected Redis client. Dependency injection makes the
                      bus independently unit-testable with a FakeRedis or mock.
    """

    def __init__(self, redis_client: redis_lib.Redis) -> None:  # type: ignore[type-arg]
        """Initialise with an injected Redis client."""
        self._redis = redis_client

    @classmethod
    def from_settings(cls) -> "EventBus":
        """
        Construct an EventBus using the centralized Redis client factory.

        Call this at the service layer or in Celery tasks where Django
        settings are available.
        """
        from core.redis_client import get_redis_client

        return cls(get_redis_client())

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    def publish_analysis_event(self, event: AnalysisEvent) -> str:
        """
        Publish an AnalysisEvent to the appropriate Redis stream.

        The stream is determined by the event's ``event_type``::

            analysis_event:price_movement
            analysis_event:volume_spike
            ...

        Args:
            event: The event to publish.

        Returns:
            The stream entry ID (a Redis auto-generated timestamp-sequence).

        Raises:
            EventBusError: If the Redis XADD fails.
        """
        stream = EventChannel.for_event_type(event.event_type)
        payload = _serialise_event(event)

        try:
            from django.conf import settings

            maxlen = settings.EVENT_STREAM_MAXLEN
            entry_id: str = self._redis.xadd(
                stream,
                {"payload": payload},
                maxlen=maxlen,
                approximate=True,
            )
            EVENT_PUBLISHED_TOTAL.labels(
                stream=stream, event_type=event.event_type.value
            ).inc()
            logger.debug(
                "event_published",
                extra={
                    "stream": stream,
                    "event_id": str(event.id),
                    "symbol": event.symbol,
                    "entry_id": entry_id,
                },
            )
            return entry_id
        except redis_lib.RedisError as exc:
            logger.error(
                "event_publish_failed",
                extra={"stream": stream, "error": str(exc)},
            )
            raise EventBusError(f"Failed to publish event to stream '{stream}'") from exc

    def publish_raw(self, stream: str, payload: dict[str, Any]) -> str:
        """
        Publish an arbitrary JSON payload to a named Redis stream.

        Use for non-AnalysisEvent messages (feed status, system alerts).

        Args:
            stream: Redis stream key (use EventChannel constants).
            payload: JSON-serialisable dict.

        Returns:
            The stream entry ID.

        Raises:
            EventBusError: If the Redis XADD fails.
        """
        try:
            message = json.dumps(payload, cls=_EventEncoder)
            from django.conf import settings

            entry_id: str = self._redis.xadd(
                stream,
                {"payload": message},
                maxlen=settings.EVENT_STREAM_MAXLEN,
                approximate=True,
            )
            EVENT_PUBLISHED_TOTAL.labels(stream=stream, event_type="raw").inc()
            return entry_id
        except redis_lib.RedisError as exc:
            raise EventBusError(f"Failed to publish to stream '{stream}'") from exc

    # ------------------------------------------------------------------
    # Subscribing
    # ------------------------------------------------------------------

    def subscribe_analysis_events(
        self,
        *event_types: EventType,
        consumer_group: str,
        consumer_name: str,
    ) -> Generator[StreamMessage, None, None]:
        """
        Subscribe to one or more analysis event streams via a consumer group.

        This is a blocking generator intended for use in long-running
        Celery workers or management commands. Run in a dedicated thread.

        Consumer groups are created idempotently — if the group already
        exists, the existing group is used (``BUSYGROUP`` is silently
        ignored).

        Args:
            event_types: One or more ``EventType`` values to subscribe to.
                         Subscribes to all analysis event types if none given.
            consumer_group: Consumer group name (e.g. ``"rule-engine"``).
            consumer_name:  Unique consumer name within the group
                            (e.g. ``"worker-1"``).

        Yields:
            ``StreamMessage(stream, entry_id, data)`` named tuples. Callers
            MUST call ``ack_event(stream, group, entry_id)`` after
            successfully processing each message.

        Example::

            bus = EventBus.from_settings()
            for msg in bus.subscribe_analysis_events(
                EventType.PRICE_MOVEMENT,
                consumer_group="rule-engine",
                consumer_name="worker-1",
            ):
                event_data = msg.data
                bus.ack_event(msg.stream, "rule-engine", msg.entry_id)
        """
        if event_types:
            streams = [EventChannel.for_event_type(et) for et in event_types]
        else:
            streams = [EventChannel.for_event_type(et) for et in EventType]

        from django.conf import settings

        group = f"{settings.EVENT_STREAM_CONSUMER_GROUP_PREFIX}:{consumer_group}"

        for stream in streams:
            try:
                self._redis.xgroup_create(stream, group, mkstream=True)
            except redis_lib.ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

        logger.info(
            "event_bus_subscribed",
            extra={
                "streams": streams,
                "group": group,
                "consumer": consumer_name,
            },
        )

        try:
            while True:
                results = self._redis.xreadgroup(
                    group,
                    consumer_name,
                    {s: ">" for s in streams},
                    block=5000,
                    count=10,
                )
                if results:
                    for stream_key, messages in results:
                        for entry_id, raw_data in messages:
                            try:
                                payload_raw = raw_data.get("payload", "{}")
                                data = json.loads(payload_raw)
                            except json.JSONDecodeError:
                                logger.warning(
                                    "event_bus_malformed_message",
                                    extra={"raw": str(payload_raw)[:200]},
                                )
                                continue
                            yield StreamMessage(
                                stream=stream_key,
                                entry_id=entry_id,
                                data=data,
                            )
        except redis_lib.RedisError as exc:
            logger.error(
                "event_bus_subscription_error",
                extra={"error": str(exc)},
            )
            raise EventBusError("Event bus subscription failed") from exc

    # ------------------------------------------------------------------
    # Acknowledgment
    # ------------------------------------------------------------------

    def ack_event(self, stream: str, consumer_group: str, entry_id: str) -> None:
        """
        Acknowledge successful processing of a stream message.

        Consumers MUST call this after successfully processing a message
        received via ``subscribe_analysis_events``. Unacknowledged messages
        remain in the consumer group's pending entries list and will be
        redelivered (via ``XAUTOCLAIM`` / ``XPENDING``) to another consumer
        if the original consumer does not respond within the idle timeout.

        Args:
            stream:         The stream key the message was read from.
            consumer_group: The consumer group name (same value passed to
                            ``subscribe_analysis_events``).
            entry_id:       The entry ID from ``StreamMessage.entry_id``.

        Raises:
            EventBusError: If the Redis XACK fails.
        """
        from django.conf import settings

        group = f"{settings.EVENT_STREAM_CONSUMER_GROUP_PREFIX}:{consumer_group}"
        try:
            self._redis.xack(stream, group, entry_id)
            EVENT_CONSUMED_TOTAL.labels(stream=stream, group=group).inc()
        except redis_lib.RedisError as exc:
            logger.error(
                "event_ack_failed",
                extra={
                    "stream": stream,
                    "group": group,
                    "entry_id": entry_id,
                    "error": str(exc),
                },
            )
            raise EventBusError(
                f"Failed to acknowledge event on stream '{stream}'"
            ) from exc

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def report_stream_metrics(
        self, streams: list[str], groups: dict[str, str]
    ) -> None:
        """
        Update Prometheus gauge metrics for stream length and pending count.

        Call this periodically (e.g. from a Celery beat task or a
        management command) to keep ``EVENT_STREAM_LENGTH`` and
        ``EVENT_STREAM_PENDING_TOTAL`` current.

        Args:
            streams: List of stream keys to report on.
            groups:  Mapping of ``{stream: consumer_group}`` to report
                     pending counts for.
        """
        for stream in streams:
            try:
                length = self._redis.xlen(stream)
                EVENT_STREAM_LENGTH.labels(stream=stream).set(length)
            except redis_lib.RedisError:
                pass

        for stream, group in groups.items():
            try:
                pending = self._redis.xpending(stream, group)
                count = pending.get("pending", 0) if isinstance(pending, dict) else 0
                EVENT_STREAM_PENDING_TOTAL.labels(
                    stream=stream, group=group
                ).set(count)
            except redis_lib.RedisError:
                pass
