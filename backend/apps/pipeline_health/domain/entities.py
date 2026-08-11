"""PIPELINE-HEALTH-1 — domain entities.

StageHeartbeat is the core entity: one row per ``(stage, symbol_scope)``
recording the most recent upstream event observed for that scope.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.pipeline_health.domain.value_objects import Stage


@dataclass(frozen=True)
class StageHeartbeat:
    """Latest observed heartbeat for a (stage, symbol_scope) pair.

    Attributes:
        stage: The pipeline stage the heartbeat belongs to.
        symbol_scope: ``"GLOBAL"`` for non-per-symbol stages (execution)
            or the exchange symbol for per-symbol stages.
        last_event_at: The ``occurred_at`` of the most recent event (NOT
            wall-clock — this keeps redelivery/replay correct).
        last_event_id: ``event_id`` of the most recent event.
        last_correlation_id: ``correlation_id`` of the most recent event.
    """

    stage: Stage
    symbol_scope: str
    last_event_at: datetime
    last_event_id: uuid.UUID
    last_correlation_id: uuid.UUID

    def is_newer_than(self, occurred_at: datetime) -> bool:
        """Return True when the given event strictly supersedes this one.

        Events carry their authoritative ``occurred_at``; redelivery of an
        older event (or an out-of-order replay) must never move the
        heartbeat backwards, hence the strict ``<`` guard.
        """
        if occurred_at.tzinfo is None or self.last_event_at.tzinfo is None:
            raise ValueError(
                "StageHeartbeat.is_newer_than requires timezone-aware datetimes"
            )
        return occurred_at > self.last_event_at
