from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.pipeline_health.domain.value_objects import Stage
from apps.pipeline_health.infrastructure.models import StageHeartbeat
from apps.pipeline_health.infrastructure.repositories import StageHeartbeatRepository

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _register(register_consumers):
    register_consumers()
    yield


def _fixed_event(
    event_type: str,
    *,
    occurred_at: datetime,
    symbol: str | None = None,
    correlation_id: uuid.UUID | None = None,
) -> DomainEvent:
    """Build an event with a caller-controlled occurred_at (true replay)."""
    payload: dict[str, object] = {}
    if symbol is not None:
        payload["symbol"] = symbol
    return DomainEvent(
        event_id=uuid.uuid4(),
        event_type=event_type,
        occurred_at=occurred_at,
        payload=payload,
        version=1,
        correlation_id=correlation_id or uuid.uuid4(),
    )


class TestRestartRecovery:
    def test_heartbeats_survive_worker_restart(self) -> None:
        """Persisted heartbeats are not lost when the bus is recreated.

        Simulates a worker restart by resetting the event-bus singleton and
        re-registering consumers: the ORM-backed heartbeat rows (the source
        of truth for staleness) must be untouched and re-readable.
        """
        from apps.eventbus.infrastructure.event_bus_factory import (
            get_event_bus,
            reset_event_bus,
        )
        from apps.pipeline_health.infrastructure.event_consumers import (
            register_consumers,
        )

        repo = StageHeartbeatRepository()
        event_id = uuid.uuid4()
        repo.upsert(
            stage=Stage.MARKET_DATA,
            symbol_scope="RELIANCE",
            last_event_at=NOW - timedelta(seconds=10),
            last_event_id=event_id,
            last_correlation_id=uuid.uuid4(),
        )

        # "restart": new bus singleton, fresh consumer registration.
        reset_event_bus()
        bus = get_event_bus()
        register_consumers(bus)

        heartbeat = StageHeartbeat.objects.get(
            stage="MARKET_DATA", symbol_scope="RELIANCE"
        )
        assert heartbeat.last_event_id == event_id
        assert StageHeartbeat.objects.count() == 1

    def test_replayed_events_do_not_duplicate_or_move_backwards(self) -> None:
        """Replay of the same event stream is idempotent after a restart.

        Re-delivering events carrying the SAME occurred_at through a freshly
        registered bus must neither create duplicate heartbeat rows nor move
        the recorded timestamp backwards.
        """
        from apps.eventbus.infrastructure.event_bus_factory import (
            get_event_bus,
            reset_event_bus,
        )
        from apps.pipeline_health.infrastructure.event_consumers import (
            register_consumers,
        )

        original_event = NOW - timedelta(minutes=1)
        correlation_id = uuid.uuid4()

        def _replay_once(bus) -> None:
            bus.publish(
                _fixed_event(
                    "intelligence.PacketBuilt",
                    occurred_at=original_event,
                    symbol="RELIANCE",
                    correlation_id=correlation_id,
                )
            )

        first_bus = get_event_bus()
        register_consumers(first_bus)
        _replay_once(first_bus)

        # Restart and replay the *same* event envelope.
        reset_event_bus()
        second_bus = get_event_bus()
        register_consumers(second_bus)
        _replay_once(second_bus)

        heartbeat = StageHeartbeat.objects.get(symbol_scope="RELIANCE")
        assert StageHeartbeat.objects.filter(symbol_scope="RELIANCE").count() == 1
        assert heartbeat.last_event_at == original_event

    def test_new_event_after_restart_advances_heartbeat(self) -> None:
        """A genuinely newer event after restart advances last_event_at."""
        from apps.eventbus.infrastructure.event_bus_factory import (
            get_event_bus,
            reset_event_bus,
        )
        from apps.pipeline_health.infrastructure.event_consumers import (
            register_consumers,
        )

        correlation_id = uuid.uuid4()

        def _publish(bus, occurred_at: datetime) -> None:
            bus.publish(
                _fixed_event(
                    "intelligence.PacketBuilt",
                    occurred_at=occurred_at,
                    symbol="RELIANCE",
                    correlation_id=correlation_id,
                )
            )

        bus = get_event_bus()
        register_consumers(bus)
        _publish(bus, NOW)

        reset_event_bus()
        bus2 = get_event_bus()
        register_consumers(bus2)
        _publish(bus2, NOW + timedelta(seconds=30))

        assert StageHeartbeat.objects.filter(symbol_scope="RELIANCE").count() == 1
        heartbeat = StageHeartbeat.objects.get(symbol_scope="RELIANCE")
        assert heartbeat.last_event_at == NOW + timedelta(seconds=30)
