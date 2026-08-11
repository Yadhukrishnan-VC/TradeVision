from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from django.db import transaction

from apps.eventbus.domain.events import DomainEvent
from apps.pipeline_health.infrastructure.models import StageHeartbeat
from apps.pipeline_health.infrastructure.repositories import StageHeartbeatRepository

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)


def _make_event(event_type: str, **payload):
    return DomainEvent.create(
        event_type=event_type,
        payload=payload,
        correlation_id=uuid.uuid4(),
    )


@pytest.fixture(autouse=True)
def _register(register_consumers):
    register_consumers()
    yield


class TestConsumerRegistration:
    def test_subscribes_to_all_watched_event_types(self, register_consumers) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        bus = get_event_bus()

        assert "marketdata.CandlesPersisted" in bus.handlers
        assert "technical_analysis.TechnicalAnalysisCompleted" in bus.handlers
        assert "intelligence.PacketBuilt" in bus.handlers
        assert "rule_engine.RuleFired" in bus.handlers
        assert "orders.OrderFilled" in bus.handlers

    def test_registration_is_idempotent(self, register_consumers) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        bus = get_event_bus()

        register_consumers(bus)
        register_consumers(bus)

        # subscribe() dedupes the same handler+group; no duplicate rows.
        assert len(bus.handlers["marketdata.CandlesPersisted"]) == 1


class TestHeartbeatRecordingThroughBus:
    def test_candles_persisted_records_market_data_heartbeat(
        self, instrument, register_consumers
    ) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        bus = get_event_bus()
        bus.publish(
            _make_event(
                "marketdata.CandlesPersisted",
                instrument_token=instrument.instrument_token,
                timeframe="1min",
                candle_count=1,
                provider="test",
            )
        )

        heartbeat = StageHeartbeat.objects.get(
            stage="MARKET_DATA",
            symbol_scope=instrument.tradingsymbol,
        )
        assert heartbeat.last_event_id

    def test_candles_persisted_unresolved_token_uses_token_scope(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        bus = get_event_bus()
        bus.publish(
            _make_event(
                "marketdata.CandlesPersisted",
                instrument_token=424242,
                timeframe="1min",
                candle_count=1,
                provider="test",
            )
        )

        heartbeat = StageHeartbeat.objects.get(stage="MARKET_DATA", symbol_scope="token:424242")
        assert heartbeat is not None

    @pytest.mark.parametrize(
        ("event_type", "symbol", "stage", "scope"),
        [
            (
                "technical_analysis.TechnicalAnalysisCompleted",
                "RELIANCE",
                "TECHNICAL_ANALYSIS",
                "RELIANCE",
            ),
            ("intelligence.PacketBuilt", "TCS", "INTELLIGENCE", "TCS"),
            ("rule_engine.RuleFired", "SBIN", "RULE_ENGINE", "SBIN"),
        ],
    )
    def test_symbol_events_record_heartbeats(
        self, event_type: str, symbol: str, stage: str, scope: str
    ) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        bus = get_event_bus()
        bus.publish(_make_event(event_type, symbol=symbol))

        heartbeat = StageHeartbeat.objects.get(stage=stage, symbol_scope=scope)
        assert heartbeat.last_correlation_id

    def test_order_filled_records_global_execution_heartbeat(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        bus = get_event_bus()
        bus.publish(
            _make_event(
                "orders.OrderFilled",
                order_id=str(uuid.uuid4()),
                account_id=str(uuid.uuid4()),
                filled_quantity="10",
                avg_fill_price="2500.00",
            )
        )

        heartbeat = StageHeartbeat.objects.get(stage="EXECUTION", symbol_scope="GLOBAL")
        assert heartbeat is not None

    def test_unknown_event_does_not_crash_or_record(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        bus = get_event_bus()
        bus.publish(_make_event("unrelated.Something", symbol="RELIANCE"))

        assert StageHeartbeat.objects.count() == 0

    def test_upsert_is_last_write_wins_per_scope(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        bus = get_event_bus()
        first = _make_event("intelligence.PacketBuilt", symbol="RELIANCE")
        second = _make_event("intelligence.PacketBuilt", symbol="RELIANCE")

        bus.publish(first)
        bus.publish(second)

        assert StageHeartbeat.objects.filter(symbol_scope="RELIANCE").count() == 1
        heartbeat = StageHeartbeat.objects.get(symbol_scope="RELIANCE")
        assert heartbeat.last_event_id == second.event_id

    def test_older_redelivery_is_a_noop(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        repo = StageHeartbeatRepository()
        bus = get_event_bus()

        newer = DomainEvent(
            event_id=uuid.uuid4(),
            event_type="intelligence.PacketBuilt",
            occurred_at=NOW,
            payload={"symbol": "RELIANCE"},
            version=1,
            correlation_id=uuid.uuid4(),
        )
        older = DomainEvent(
            event_id=uuid.uuid4(),
            event_type="intelligence.PacketBuilt",
            occurred_at=NOW - timedelta(minutes=5),
            payload={"symbol": "RELIANCE"},
            version=1,
            correlation_id=uuid.uuid4(),
        )

        with transaction.atomic():
            bus.publish(newer)

        with transaction.atomic():
            bus.publish(older)

        heartbeat = StageHeartbeat.objects.get(symbol_scope="RELIANCE")
        assert heartbeat.last_event_id == newer.event_id
