from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.pipeline_health.application.health_evaluation_service import (
    get_health_evaluation_service,
)
from apps.pipeline_health.domain.value_objects import Stage
from apps.pipeline_health.infrastructure.models import (
    PipelineHealthSnapshot,
    StageHeartbeat,
)
from apps.pipeline_health.infrastructure.repositories import StageHeartbeatRepository

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def market_open(monkeypatch) -> None:
    from apps.pipeline_health.application import health_evaluation_service as mod

    class _Calendar:
        def is_market_hours(self, _dt) -> bool:
            return True

    monkeypatch.setattr(mod, "get_market_calendar", lambda: _Calendar())


@pytest.fixture
def market_closed(monkeypatch) -> None:
    from apps.pipeline_health.application import health_evaluation_service as mod

    class _Calendar:
        def is_market_hours(self, _dt) -> bool:
            return False

    monkeypatch.setattr(mod, "get_market_calendar", lambda: _Calendar())


def _seed_fresh_heartbeats() -> None:
    repo = StageHeartbeatRepository()
    scopes = {
        "MARKET_DATA": "RELIANCE",
        "TECHNICAL_ANALYSIS": "RELIANCE",
        "INTELLIGENCE": "RELIANCE",
        "RULE_ENGINE": "RELIANCE",
        "EXECUTION": "GLOBAL",
    }
    for stage, scope in scopes.items():
        repo.upsert(
            stage=Stage(stage),
            symbol_scope=scope,
            last_event_at=NOW - timedelta(seconds=10),
            last_event_id=uuid.uuid4(),
            last_correlation_id=uuid.uuid4(),
        )


class TestStallDetectionIntegration:
    def test_healthy_snapshot_persisted(self, market_open) -> None:
        _seed_fresh_heartbeats()
        service = get_health_evaluation_service()

        status = service.evaluate(reference=NOW)

        assert status.value == "HEALTHY"
        snapshot = PipelineHealthSnapshot.objects.first()
        assert snapshot is not None
        assert snapshot.overall_status == "HEALTHY"
        assert snapshot.stage_statuses == {
            stage: "HEALTHY" for stage in ("MARKET_DATA", "TECHNICAL_ANALYSIS",
                                           "INTELLIGENCE", "RULE_ENGINE", "EXECUTION")
        }

    def test_stale_stage_triggers_stalled_and_event(self, market_open) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        _seed_fresh_heartbeats()
        StageHeartbeat.objects.filter(stage="MARKET_DATA").update(
            last_event_at=NOW - timedelta(hours=1)
        )
        service = get_health_evaluation_service()

        status = service.evaluate(reference=NOW)

        assert status.value == "STALLED"
        snapshot = PipelineHealthSnapshot.objects.first()
        assert snapshot.stage_statuses["MARKET_DATA"] == "STALLED"

        bus = get_event_bus()
        stalled = [
            e for e in bus.published_events if e.event_type == "pipeline_health.StageStalled"
        ]
        assert len(stalled) == 1
        assert stalled[0].payload["stalled_stages"][0]["stage"] == "MARKET_DATA"

    def test_repeated_stalled_does_not_republish(self, market_open) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        _seed_fresh_heartbeats()
        StageHeartbeat.objects.filter(stage="RULE_ENGINE").update(
            last_event_at=NOW - timedelta(hours=1)
        )
        service = get_health_evaluation_service()

        service.evaluate(reference=NOW)
        service.evaluate(reference=NOW + timedelta(seconds=30))
        service.evaluate(reference=NOW + timedelta(seconds=60))

        bus = get_event_bus()
        stalled = [
            e for e in bus.published_events if e.event_type == "pipeline_health.StageStalled"
        ]
        assert len(stalled) == 1

    def test_market_closed_does_not_persist_snapshot(self, market_closed) -> None:
        _seed_fresh_heartbeats()
        service = get_health_evaluation_service()

        status = service.evaluate(reference=NOW)

        assert status.value == "HEALTHY"
        assert PipelineHealthSnapshot.objects.count() == 0

    def test_evaluation_does_not_modify_heartbeats(self, market_open) -> None:
        _seed_fresh_heartbeats()
        before = {
            (h.stage, h.symbol_scope): h.last_event_at
            for h in StageHeartbeat.objects.all()
        }

        get_health_evaluation_service().evaluate(reference=NOW)

        after = {
            (h.stage, h.symbol_scope): h.last_event_at
            for h in StageHeartbeat.objects.all()
        }
        assert before == after


class TestStageStalledEventEnvelope:
    def test_event_has_expected_envelope_fields(self, market_open) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        _seed_fresh_heartbeats()
        StageHeartbeat.objects.filter(stage="EXECUTION").update(
            last_event_at=NOW - timedelta(hours=2)
        )
        service = get_health_evaluation_service()

        service.evaluate(reference=NOW)

        bus = get_event_bus()
        stalled = [
            e for e in bus.published_events if e.event_type == "pipeline_health.StageStalled"
        ]
        assert len(stalled) == 1
        event = stalled[0]
        assert event.version == 1
        assert event.correlation_id is not None
        assert event.payload["stalled_stages"][0]["symbol_scope"] == "GLOBAL"
