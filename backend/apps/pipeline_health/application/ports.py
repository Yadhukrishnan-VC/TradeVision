"""PIPELINE-HEALTH-1 — application ports (interfaces).

The application services depend only on these protocols, never on Django
ORM models directly, keeping the staleness logic testable with fakes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from apps.eventbus.domain.events import DomainEvent
from apps.pipeline_health.domain.value_objects import Stage


class StageHeartbeatRepository(Protocol):
    """Persistence interface for stage heartbeats."""

    def upsert(
        self,
        *,
        stage: Stage,
        symbol_scope: str,
        last_event_at: datetime,
        last_event_id: uuid.UUID,
        last_correlation_id: uuid.UUID,
    ) -> None:
        """Insert or update the heartbeat for (stage, symbol_scope).

        Idempotent last-write-wins on the natural key: an event whose
        ``occurred_at`` is not newer than the stored heartbeat is a no-op.
        """
        ...

    def latest_for_stage(self, stage: Stage) -> tuple[str, datetime] | None:
        """Return the newest (symbol_scope, last_event_at) for a stage.

        Returns ``None`` when the stage has never produced a heartbeat.
        """
        ...


class PipelineHealthSnapshotRepository(Protocol):
    """Persistence interface for evaluated health snapshots."""

    def save(
        self,
        *,
        evaluated_at: datetime,
        overall_status: str,
        stage_statuses: dict[str, object],
    ) -> object:
        """Persist a new snapshot and return it."""
        ...

    def latest(self) -> object | None:
        """Return the most recently evaluated snapshot, or None."""
        ...


class EventPublisher(Protocol):
    """Publish a domain event out of the pipeline-health context."""

    def publish(self, event: DomainEvent) -> None:
        """Publish the given event to the configured EventBus."""
        ...
