from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.pipeline_health.application.health_evaluation_service import (
    HealthEvaluationService,
)
from apps.pipeline_health.domain.value_objects import (
    PipelineHealthStatus,
    Stage,
)


class _HeartbeatRepo:
    """In-memory fake: stage -> newest (symbol_scope, last_event_at)."""

    def __init__(self) -> None:
        self._latest: dict[str, tuple[str, datetime]] = {}

    def upsert(self, **kwargs) -> None:  # noqa: ARG002 - protocol stub
        raise NotImplementedError

    def seed(self, stage: Stage, symbol_scope: str, last_event_at: datetime) -> None:
        self._latest[stage.value] = (symbol_scope, last_event_at)

    def latest_for_stage(self, stage: Stage) -> tuple[str, datetime] | None:
        return self._latest.get(stage.value)


class _Snapshot:
    def __init__(self, **kwargs) -> None:
        self.evaluated_at = kwargs["evaluated_at"]
        self.overall_status = kwargs["overall_status"]
        self.stage_statuses = kwargs["stage_statuses"]


class _SnapshotRepo:
    """In-memory fake capturing saved snapshots and the latest record."""

    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []
        self._previous: _Snapshot | None = None

    def save(self, **kwargs) -> object:
        self.saved.append(kwargs)
        self._previous = _Snapshot(**kwargs)
        return self._previous

    def latest(self) -> object | None:
        return self._previous


class _Publisher:
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.published.append(event)


def _fresh_heartbeats(now: datetime) -> _HeartbeatRepo:
    repo = _HeartbeatRepo()
    for stage, scope in [
        (Stage.MARKET_DATA, "RELIANCE"),
        (Stage.TECHNICAL_ANALYSIS, "RELIANCE"),
        (Stage.INTELLIGENCE, "RELIANCE"),
        (Stage.RULE_ENGINE, "RELIANCE"),
        (Stage.EXECUTION, "GLOBAL"),
    ]:
        repo.seed(stage, scope, now - timedelta(seconds=10))
    return repo


def _build_service(heartbeats, snapshots, publisher):
    return HealthEvaluationService(
        heartbeat_repository=heartbeats,
        snapshot_repository=snapshots,
        event_publisher=publisher,
    )


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


NOW = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)


class TestHealthEvaluation:
    def test_all_stages_fresh_returns_healthy(self, market_open) -> None:
        heartbeats = _fresh_heartbeats(NOW)
        snapshots = _SnapshotRepo()
        service = _build_service(heartbeats, snapshots, _Publisher())

        status = service.evaluate(reference=NOW)

        assert status == PipelineHealthStatus.HEALTHY
        assert len(snapshots.saved) == 1
        assert snapshots.saved[0]["overall_status"] == PipelineHealthStatus.HEALTHY.value
        for stage in Stage:
            assert snapshots.saved[0]["stage_statuses"][stage.value] == "HEALTHY"

    def test_single_stalled_stage_rolls_up_to_stalled(self, market_open) -> None:
        heartbeats = _fresh_heartbeats(NOW)
        heartbeats.seed(Stage.MARKET_DATA, "RELIANCE", NOW - timedelta(hours=1))
        snapshots = _SnapshotRepo()
        publisher = _Publisher()
        service = _build_service(heartbeats, snapshots, publisher)

        status = service.evaluate(reference=NOW)

        assert status == PipelineHealthStatus.STALLED
        assert snapshots.saved[0]["stage_statuses"][Stage.MARKET_DATA.value] == "STALLED"

    def test_publishes_stalled_only_on_first_transition(self, market_open) -> None:
        heartbeats = _fresh_heartbeats(NOW)
        snapshots = _SnapshotRepo()
        publisher = _Publisher()
        service = _build_service(heartbeats, snapshots, publisher)

        heartbeats.seed(Stage.MARKET_DATA, "RELIANCE", NOW - timedelta(hours=1))
        service.evaluate(reference=NOW)
        service.evaluate(reference=NOW + timedelta(seconds=30))

        stalled_events = [
            e for e in publisher.published if e.event_type == "pipeline_health.StageStalled"
        ]
        assert len(stalled_events) == 1
        assert stalled_events[0].payload["stalled_stages"][0]["stage"] == "MARKET_DATA"

    def test_recovery_to_healthy_publishes_nothing(self, market_open) -> None:
        heartbeats = _fresh_heartbeats(NOW)
        snapshots = _SnapshotRepo()
        publisher = _Publisher()
        service = _build_service(heartbeats, snapshots, publisher)

        heartbeats.seed(Stage.MARKET_DATA, "RELIANCE", NOW - timedelta(hours=1))
        service.evaluate(reference=NOW)
        # stage recovers
        heartbeats.seed(Stage.MARKET_DATA, "RELIANCE", NOW + timedelta(seconds=30))
        service.evaluate(reference=NOW + timedelta(seconds=30))

        stalled_events = [
            e for e in publisher.published if e.event_type == "pipeline_health.StageStalled"
        ]
        assert len(stalled_events) == 1  # only the original transition

    def test_market_closed_short_circuits_no_snapshot(self, market_closed) -> None:
        heartbeats = _fresh_heartbeats(NOW)
        snapshots = _SnapshotRepo()
        service = _build_service(heartbeats, snapshots, _Publisher())

        status = service.evaluate(reference=NOW)

        assert status == PipelineHealthStatus.HEALTHY
        assert snapshots.saved == []
        assert heartbeats.latest_for_stage(Stage.MARKET_DATA) is not None

    def test_no_heartbeat_for_stage_is_not_stalled(self, market_open) -> None:
        heartbeats = _HeartbeatRepo()
        snapshots = _SnapshotRepo()
        service = _build_service(heartbeats, snapshots, _Publisher())

        status = service.evaluate(reference=NOW)

        assert status == PipelineHealthStatus.HEALTHY
        for stage in Stage:
            assert snapshots.saved[0]["stage_statuses"][stage.value] == "HEALTHY"

    def test_stalled_event_carries_correlation_and_payload(self, market_open) -> None:
        heartbeats = _fresh_heartbeats(NOW)
        heartbeats.seed(Stage.RULE_ENGINE, "SBIN", NOW - timedelta(hours=1))
        snapshots = _SnapshotRepo()
        publisher = _Publisher()
        service = _build_service(heartbeats, snapshots, publisher)

        service.evaluate(reference=NOW)

        stalled_events = [
            e for e in publisher.published if e.event_type == "pipeline_health.StageStalled"
        ]
        assert len(stalled_events) == 1
        payload = stalled_events[0].payload
        assert payload["evaluated_at"] == NOW.isoformat()
        assert payload["stalled_stages"][0]["stage"] == "RULE_ENGINE"
        assert payload["stalled_stages"][0]["symbol_scope"] == "SBIN"
