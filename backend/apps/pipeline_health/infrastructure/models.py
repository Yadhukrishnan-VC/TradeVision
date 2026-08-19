"""PIPELINE-HEALTH-1 — Django ORM models.

``StageHeartbeat`` is the ingest side (one row per stage+scope, last-write
wins). ``PipelineHealthSnapshot`` is the read side (operator-facing rollup
of the last evaluation).
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.pipeline_health.domain.value_objects import (
    PipelineHealthStatus,
    Stage,
)
from core.models import BaseModel


class StageHeartbeat(BaseModel):
    """Latest observed heartbeat for a (stage, symbol_scope) pair.

    ``last_event_at`` is the upstream event's ``occurred_at`` (not
    wall-clock), so replay/redelivery can never move the heartbeat
    backwards.
    """

    stage = models.CharField(max_length=32, choices=Stage.choices())
    symbol_scope = models.CharField(max_length=32)
    last_event_at = models.DateTimeField()
    last_event_id = models.UUIDField()
    last_correlation_id = models.UUIDField()

    class Meta:
        db_table = "pipeline_health_stageheartbeat"
        verbose_name = "Stage Heartbeat"
        verbose_name_plural = "Stage Heartbeats"
        constraints = [
            models.UniqueConstraint(
                fields=["stage", "symbol_scope"],
                name="uq_stage_heartbeat_stage_scope",
            ),
        ]
        indexes = [
            models.Index(
                fields=["stage", "last_event_at"],
                name="idx_stage_heartbeat_evt",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"StageHeartbeat({self.stage}/{self.symbol_scope} "
            f"@ {self.last_event_at})"
        )


class PipelineHealthSnapshot(BaseModel):
    """Rolled-up health snapshot persisted by the evaluation service.

    ``stage_statuses`` is a JSON object keyed by stage name whose values are
    the per-stage status string (HEALTHY / DEGRADED / STALLED).
    """

    evaluated_at = models.DateTimeField(db_index=True)
    overall_status = models.CharField(
        max_length=16,
        choices=PipelineHealthStatus.choices(),
    )
    stage_statuses = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "pipeline_health_pipelinehealthsnapshot"
        verbose_name = "Pipeline Health Snapshot"
        verbose_name_plural = "Pipeline Health Snapshots"
        ordering = ["-evaluated_at"]

    def __str__(self) -> str:
        return f"PipelineHealthSnapshot({self.overall_status} @ {self.evaluated_at})"
