"""PIPELINE-HEALTH-1 — health evaluation service.

Evaluates the freshness of every watched stage against its
``StageExpectation`` during market hours, persists a
``PipelineHealthSnapshot``, and publishes a ``pipeline_health.StageStalled``
event only on a HEALTHY→STALLED transition (mirroring the
``marketdata.SessionStatusChanged`` convention of publishing on actual
transitions only).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.pipeline_health.application.ports import (
    EventPublisher,
    PipelineHealthSnapshotRepository,
    StageHeartbeatRepository,
)
from apps.pipeline_health.domain.value_objects import (
    PipelineHealthStatus,
    Stage,
    StageExpectation,
)
from core.market_calendar import get_market_calendar
from core.metrics import (
    PIPELINE_HEALTH_STATUS,
    PIPELINE_STAGE_STALENESS_SECONDS,
    PIPELINE_STALLED_TOTAL,
)
from core.utils import get_now

logger = logging.getLogger(__name__)


class HealthEvaluationService:
    """Compute and persist pipeline health snapshots."""

    def __init__(
        self,
        heartbeat_repository: StageHeartbeatRepository,
        snapshot_repository: PipelineHealthSnapshotRepository,
        event_publisher: EventPublisher,
    ) -> None:
        self._heartbeats = heartbeat_repository
        self._snapshots = snapshot_repository
        self._publisher = event_publisher
        self._calendar = get_market_calendar()

    def evaluate(self, reference: datetime | None = None) -> PipelineHealthStatus:
        """Evaluate pipeline health for the current market session.

        Args:
            reference: Optional comparison instant (UTC-aware); defaults to
                now (UTC).

        Returns:
            The overall ``PipelineHealthStatus`` computed and persisted. When
            the market is closed the service short-circuits and returns
            ``PipelineHealthStatus.HEALTHY`` without persisting a snapshot.
        """
        now = reference if reference is not None else get_now()
        market_open = self._calendar.is_market_hours(now)

        if not market_open:
            logger.info("pipeline_health_evaluation_skipped_market_closed")
            return PipelineHealthStatus.HEALTHY

        previous = self._snapshots.latest()

        stage_statuses: dict[str, Any] = {}
        stalled_stages: list[dict[str, str]] = []

        for stage in Stage:
            expectation = StageExpectation.for_stage(stage, market_open=market_open)
            status = PipelineHealthStatus.HEALTHY.value

            latest = self._heartbeats.latest_for_stage(stage)
            if latest is not None:
                symbol_scope, last_event_at = latest
                staleness_seconds = int((now - last_event_at).total_seconds())
                PIPELINE_STAGE_STALENESS_SECONDS.labels(
                    stage=stage.value, symbol_scope=symbol_scope
                ).set(staleness_seconds)

                if expectation.is_stalled(last_event_at, reference=now):
                    status = PipelineHealthStatus.STALLED.value
                    stalled_stages.append(
                        {
                            "stage": stage.value,
                            "symbol_scope": symbol_scope,
                            "last_event_at": last_event_at.isoformat(),
                            "staleness_seconds": str(staleness_seconds),
                        }
                    )

            stage_statuses[stage.value] = status
            PIPELINE_HEALTH_STATUS.labels(stage=stage.value).set(
                _status_to_metric(status)
            )

        overall = self._rollup(stage_statuses)
        self._snapshots.save(
            evaluated_at=now,
            overall_status=overall.value,
            stage_statuses=stage_statuses,
        )

        self._maybe_publish_stalled(overall, now, stalled_stages, previous)
        return overall

    def _maybe_publish_stalled(
        self,
        overall: PipelineHealthStatus,
        evaluated_at: datetime,
        stalled_stages: list[dict[str, str]],
        previous: Any,
    ) -> None:
        """Publish ``pipeline_health.StageStalled`` on HEALTHY→STALLED only.

        The transition reference is the snapshot persisted before this
        evaluation. No snapshot yet (first evaluation) or a previous
        non-STALLED snapshot both qualify as the "HEALTHY" side of the
        transition; a repeated STALLED evaluation does not republish.
        """
        if overall != PipelineHealthStatus.STALLED:
            return

        if previous is not None and getattr(previous, "overall_status", None) == (
            PipelineHealthStatus.STALLED.value
        ):
            return

        for stage_info in stalled_stages:
            PIPELINE_STALLED_TOTAL.labels(stage=stage_info["stage"]).inc()

        event = DomainEvent.create(
            event_type="pipeline_health.StageStalled",
            payload={
                "evaluated_at": evaluated_at.isoformat(),
                "stalled_stages": stalled_stages,
            },
            correlation_id=uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"pipeline_health.StageStalled:{evaluated_at.isoformat()}",
            ),
            version=1,
        )
        try:
            self._publisher.publish(event)
        except Exception:
            logger.exception(
                "pipeline_health_stalled_publish_failed",
                extra={"evaluated_at": evaluated_at.isoformat()},
            )

    @staticmethod
    def _rollup(
        stage_statuses: dict[str, str],
    ) -> PipelineHealthStatus:
        """Roll per-stage statuses into an overall status.

        STALLED if any watched stage is stalled during market hours;
        DEGRADED if a non-critical stage is stale (e.g. the WATCH-1 quote
        enrichment path); HEALTHY otherwise.
        """
        values = set(stage_statuses.values())
        if PipelineHealthStatus.STALLED.value in values:
            return PipelineHealthStatus.STALLED
        if PipelineHealthStatus.DEGRADED.value in values:
            return PipelineHealthStatus.DEGRADED
        return PipelineHealthStatus.HEALTHY


def _status_to_metric(status: str) -> float:
    """Map a status string to the Prometheus gauge value."""
    return {
        PipelineHealthStatus.HEALTHY.value: 0.0,
        PipelineHealthStatus.DEGRADED.value: 1.0,
        PipelineHealthStatus.STALLED.value: 2.0,
    }.get(status, 0.0)


def get_health_evaluation_service() -> HealthEvaluationService:
    """Build the service with the production infrastructure wiring."""
    from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
    from apps.pipeline_health.infrastructure.repositories import (
        PipelineHealthSnapshotRepository,
        StageHeartbeatRepository,
    )

    return HealthEvaluationService(
        heartbeat_repository=StageHeartbeatRepository(),
        snapshot_repository=PipelineHealthSnapshotRepository(),
        event_publisher=get_event_bus(),
    )
