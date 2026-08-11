"""PIPELINE-HEALTH-1 — Django ORM repositories.

Both repositories implement the application-layer protocols from
``apps.pipeline_health.application.ports``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from django.db import transaction

from apps.pipeline_health.domain.value_objects import Stage
from apps.pipeline_health.infrastructure.models import (
    PipelineHealthSnapshot,
    StageHeartbeat,
)


class StageHeartbeatRepository:
    """Persistence for ``StageHeartbeat`` rows.

    Idempotent last-write-wins on the (stage, symbol_scope) natural key.
    The stale-redelivery guard lives here, at the persistence boundary,
    using ``event.occurred_at < stored last_event_at`` semantics.
    """

    def upsert(
        self,
        *,
        stage: Stage,
        symbol_scope: str,
        last_event_at: datetime,
        last_event_id: uuid.UUID,
        last_correlation_id: uuid.UUID,
    ) -> None:
        with transaction.atomic():
            heartbeat = StageHeartbeat.objects.select_for_update().filter(
                stage=stage.value,
                symbol_scope=symbol_scope,
            ).first()

            if heartbeat is None:
                StageHeartbeat.objects.create(
                    stage=stage.value,
                    symbol_scope=symbol_scope,
                    last_event_at=last_event_at,
                    last_event_id=last_event_id,
                    last_correlation_id=last_correlation_id,
                )
                return

            if last_event_at > heartbeat.last_event_at:
                heartbeat.last_event_at = last_event_at
                heartbeat.last_event_id = last_event_id
                heartbeat.last_correlation_id = last_correlation_id
                heartbeat.save(
                    update_fields=[
                        "last_event_at",
                        "last_event_id",
                        "last_correlation_id",
                        "updated_at",
                    ]
                )

    def latest_for_stage(self, stage: Stage) -> tuple[str, datetime] | None:
        """Return the newest (symbol_scope, last_event_at) for a stage."""
        heartbeat = (
            StageHeartbeat.objects.filter(stage=stage.value)
            .order_by("-last_event_at")
            .first()
        )
        if heartbeat is None:
            return None
        return heartbeat.symbol_scope, heartbeat.last_event_at

    def all_heartbeats(self) -> list[dict[str, Any]]:
        """Return every heartbeat row as a plain dict (operator view)."""
        rows = StageHeartbeat.objects.all()
        return [
            {
                "stage": row.stage,
                "symbol_scope": row.symbol_scope,
                "last_event_at": row.last_event_at,
                "last_event_id": row.last_event_id,
                "last_correlation_id": row.last_correlation_id,
            }
            for row in rows
        ]


class PipelineHealthSnapshotRepository:
    """Persistence for ``PipelineHealthSnapshot`` rows."""

    def save(
        self,
        *,
        evaluated_at: datetime,
        overall_status: str,
        stage_statuses: dict[str, object],
    ) -> PipelineHealthSnapshot:
        return PipelineHealthSnapshot.objects.create(
            evaluated_at=evaluated_at,
            overall_status=overall_status,
            stage_statuses=stage_statuses,
        )

    def latest(self) -> PipelineHealthSnapshot | None:
        return PipelineHealthSnapshot.objects.first()

    def list_recent(self, limit: int = 20) -> list[PipelineHealthSnapshot]:
        return list(PipelineHealthSnapshot.objects.all()[:limit])
