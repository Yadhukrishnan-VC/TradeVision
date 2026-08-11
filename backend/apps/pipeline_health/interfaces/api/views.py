"""PIPELINE-HEALTH-1 — API views.

Read-only operator endpoint exposing the latest evaluated pipeline health
snapshot and the current per-stage heartbeats.
"""

from __future__ import annotations

from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.pipeline_health.interfaces.api.serializers import (
    PipelineHealthSerializer,
)
from apps.pipeline_health.infrastructure.repositories import (
    PipelineHealthSnapshotRepository,
    StageHeartbeatRepository,
)


class PipelineHealthView(GenericAPIView):
    """GET /api/v1/pipeline-health/ — current forward-pipeline health.

    Returns the most recently evaluated snapshot (rolled-up overall status
    and per-stage statuses) plus the raw per-stage heartbeats. When no
    snapshot has been evaluated yet (e.g. outside market hours or right
    after deploy), ``snapshot`` is omitted and only ``heartbeats`` is
    returned.
    """

    serializer_class = PipelineHealthSerializer

    def __init__(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(**kwargs)
        self._snapshots = PipelineHealthSnapshotRepository()
        self._heartbeats = StageHeartbeatRepository()

    def get(self, request: Request) -> Response:  # noqa: ARG002 - DRF signature
        snapshot = self._snapshots.latest()
        heartbeat_rows = self._heartbeats.all_heartbeats()

        data: dict[str, object] = {"heartbeats": heartbeat_rows}
        if snapshot is not None:
            data["snapshot"] = {
                "evaluated_at": snapshot.evaluated_at,
                "overall_status": snapshot.overall_status,
                "stage_statuses": snapshot.stage_statuses,
            }

        serializer = self.get_serializer(data)
        return Response(serializer.data)
