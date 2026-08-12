"""PORTFOLIO-RECONCILE-1 — API serializers."""

from __future__ import annotations

from rest_framework import serializers

from apps.portfolio_reconciliation.infrastructure.models import DriftRecord


class DriftRecordSerializer(serializers.ModelSerializer):
    """Read-only view of one persisted drift record."""

    classification = serializers.CharField()
    entity_type = serializers.CharField()

    class Meta:
        model = DriftRecord
        fields = [
            "account_id",
            "entity_type",
            "entity_key",
            "classification",
            "auto_repaired",
            "detected_at",
            "repaired_at",
            "expected_snapshot",
            "actual_snapshot",
        ]
        read_only_fields = fields


class DriftSummarySerializer(serializers.Serializer):
    """Counts by classification plus the last run timestamp."""

    classification_breakdown = serializers.DictField(child=serializers.IntegerField())
    total_records = serializers.IntegerField()
    last_run_at = serializers.DateTimeField(allow_null=True)