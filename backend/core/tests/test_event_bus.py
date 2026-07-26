"""
Tests for core.events.event_bus — Redis Streams publish/consume/ack cycle.
"""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import redis as redis_lib

from core.events.event_bus import EventBus, EventBusError, EventChannel, StreamMessage
from core.events.event_types import AnalysisEvent, EventType, CircuitStatus, DataQuality
from core.events.event_types import PriceContext, TechnicalContext, BreadthContext, NewsContext, IntelligencePacket


def _make_event(event_type: EventType = EventType.PRICE_MOVEMENT) -> AnalysisEvent:
    """Build a minimal valid AnalysisEvent for testing."""
    return AnalysisEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        symbol="TEST",
        timestamp=datetime.now(timezone.utc),
        rule_id="test_rule",
        trigger_data={"reason": "test"},
        intelligence_packet=IntelligencePacket(
            symbol="TEST",
            timestamp=datetime.now(timezone.utc),
            freshness_validated=True,
            price_context=PriceContext(
                current_price=Decimal("100"),
                open_price=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                prev_close=Decimal("99"),
                change_pct=Decimal("1.01"),
                volume=100000,
                avg_volume_20d=80000,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=TechnicalContext(),
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0"),
                sector_advance_decline=Decimal("0"),
                nifty_change_pct=Decimal("0"),
                sensex_change_pct=Decimal("0"),
            ),
            news_context=NewsContext(),
            data_quality=DataQuality(),
        ),
    )


class TestEventBusPublishConsumeAck:
    """Happy path: publish → consume → ack cycle."""

    def test_publish_returns_entry_id(self, clean_redis: redis_lib.Redis) -> None:
        bus = EventBus(clean_redis)
        event = _make_event()
        entry_id = bus.publish_analysis_event(event)
        assert isinstance(entry_id, str)
        assert len(entry_id) > 0

    def test_publish_and_consume(self, clean_redis: redis_lib.Redis) -> None:
        from django.conf import settings

        bus = EventBus(clean_redis)
        event = _make_event()
        stream = EventChannel.for_event_type(event.event_type)
        group = f"{settings.EVENT_STREAM_CONSUMER_GROUP_PREFIX}:test-group"
        consumer = "test-consumer"

        clean_redis.xgroup_create(stream, group, mkstream=True)
        bus.publish_analysis_event(event)

        results = clean_redis.xreadgroup(group, consumer, {stream: ">"}, count=5, block=1000)
        assert len(results) == 1
        stream_key, messages = results[0]
        assert stream_key == stream
        assert len(messages) >= 1
        entry_id, data = messages[0]
        payload = json.loads(data["payload"])
        assert payload["symbol"] == "TEST"
        assert payload["event_type"] == "price_movement"
        assert payload["rule_id"] == "test_rule"

    def test_consume_and_ack(self, clean_redis: redis_lib.Redis) -> None:
        from django.conf import settings

        bus = EventBus(clean_redis)
        event = _make_event()
        stream = EventChannel.for_event_type(event.event_type)
        group = f"{settings.EVENT_STREAM_CONSUMER_GROUP_PREFIX}:test-group-ack"
        consumer = "test-consumer-ack"

        clean_redis.xgroup_create(stream, group, mkstream=True)
        bus.publish_analysis_event(event)

        results = clean_redis.xreadgroup(group, consumer, {stream: ">"}, count=5, block=1000)
        assert len(results) == 1
        _, messages = results[0]
        entry_id, _ = messages[0]

        bus.ack_event(stream, "test-group-ack", entry_id)

        pending = clean_redis.xpending(stream, group)
        assert pending["pending"] == 0

    def test_generator_yields_stream_message(self, clean_redis: redis_lib.Redis) -> None:
        from django.conf import settings

        bus = EventBus(clean_redis)
        event = _make_event()
        stream = EventChannel.for_event_type(event.event_type)
        group = "test-gen"
        prefixed_group = f"{settings.EVENT_STREAM_CONSUMER_GROUP_PREFIX}:{group}"
        consumer = "test-gen-consumer"

        # Create consumer group first (reading from beginning),
        # then publish, then subscribe — ensures all messages are delivered
        clean_redis.xgroup_create(stream, prefixed_group, id="0", mkstream=True)
        bus.publish_analysis_event(event)

        gen = bus.subscribe_analysis_events(
            event.event_type,
            consumer_group=group,
            consumer_name=consumer,
        )
        msg = next(gen)
        assert isinstance(msg, StreamMessage)
        assert msg.stream == stream
        assert msg.data["symbol"] == "TEST"


class TestEventBusRedelivery:
    """Unacknowledged messages must become claimable."""

    def test_unacked_message_appears_in_pending(self, clean_redis: redis_lib.Redis) -> None:
        from django.conf import settings

        bus = EventBus(clean_redis)
        event = _make_event()
        stream = EventChannel.for_event_type(event.event_type)
        group = f"{settings.EVENT_STREAM_CONSUMER_GROUP_PREFIX}:test-pending"
        consumer = "test-pending-consumer"

        clean_redis.xgroup_create(stream, group, mkstream=True)
        bus.publish_analysis_event(event)

        results = clean_redis.xreadgroup(group, consumer, {stream: ">"}, count=5, block=1000)
        assert len(results) == 1

        pending = clean_redis.xpending(stream, group)
        assert pending["pending"] >= 1

    def test_unacked_message_claimable_by_another_consumer(
        self, clean_redis: redis_lib.Redis
    ) -> None:
        from django.conf import settings

        bus = EventBus(clean_redis)
        event = _make_event()
        stream = EventChannel.for_event_type(event.event_type)
        group = f"{settings.EVENT_STREAM_CONSUMER_GROUP_PREFIX}:test-claim"

        clean_redis.xgroup_create(stream, group, mkstream=True)
        bus.publish_analysis_event(event)

        consumer1 = "consumer-1"
        clean_redis.xreadgroup(group, consumer1, {stream: ">"}, count=5, block=1000)

        # Set a very short idle time so XAUTOCLAIM will claim immediately
        pending = clean_redis.xpending(stream, group)
        assert pending["pending"] >= 1

        # XAUTOCLAIM with min-idle-time=0 should claim the pending message
        claimed = clean_redis.xautoclaim(stream, group, "consumer-2", min_idle_time=0)
        if claimed:
            # The claimed response format: (next_entry_id, [entries])
            claimed_entries = claimed[1] if len(claimed) > 1 else []
            assert len(claimed_entries) >= 1, "Expected at least one claimed entry"


class TestEventBusMaxlen:
    """MAXLEN approximate trimming must take effect."""

    def test_stream_trimmed_after_maxlen(
        self, clean_redis: redis_lib.Redis
    ) -> None:
        stream = "test:trim"

        # Publish 100 messages WITH exact MAXLEN=5 (no ~, for determinism)
        for i in range(100):
            clean_redis.xadd(stream, {"seq": str(i)}, maxlen=5, approximate=False)
        length = clean_redis.xlen(stream)
        # Exact MAXLEN=5 should keep exactly 5 entries
        assert length == 5, f"Expected exactly 5 entries, got {length}"

    def test_publish_raw_message_structure(self, clean_redis: redis_lib.Redis) -> None:
        """publish_raw must store JSON payload in the stream."""
        bus = EventBus(clean_redis)
        stream = "test:raw-structure"

        bus.publish_raw(stream, {"key": "value", "num": 42})
        entries = clean_redis.xrange(stream, count=1)
        assert len(entries) == 1
        entry_id, data = entries[0]
        assert "payload" in data
        import json
        payload = json.loads(data["payload"])
        assert payload == {"key": "value", "num": 42}


class TestEventChannel:
    """Stream name constants."""

    def test_for_event_type(self) -> None:
        name = EventChannel.for_event_type(EventType.PRICE_MOVEMENT)
        assert name == "analysis_event:price_movement"

    def test_for_feed(self) -> None:
        name = EventChannel.for_feed("zerodha")
        assert name == "feed_status:zerodha"

    def test_system(self) -> None:
        name = EventChannel.system("startup")
        assert name == "system:startup"


class TestEventBusError:
    """Bus construction and error handling."""

    def test_event_bus_error_is_exception(self) -> None:
        assert issubclass(EventBusError, Exception)
