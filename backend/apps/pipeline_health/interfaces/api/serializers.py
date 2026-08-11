"""PIPELINE-HEALTH-1 — API serializers."""

from __future__ import annotations

from rest_framework import serializers


class StageHeartbeatSerializer(serializers.Serializer):
    """Per-stage heartbeat row for the operator view."""

    stage = serializers.CharField()
    symbol_scope = serializers.CharField()
    last_event_at = serializers.DateTimeField()


class PipelineHealthSnapshotSerializer(serializers.Serializer):
    """The latest evaluated pipeline health snapshot."""

    evaluated_at = serializers.DateTimeField()
    overall_status = serializers.CharField()
    stage_statuses = serializers.DictField(child=serializers.CharField())


class PipelineHealthSerializer(serializers.Serializer):
    """Combined operator-facing health payload.

    Returns the latest snapshot plus the current per-stage heartbeats so an
    operator can see both the rolled-up status and the underlying data.
    """

    snapshot = PipelineHealthSnapshotSerializer(required=False)
    heartbeats = StageHeartbeatSerializer(many=True)
