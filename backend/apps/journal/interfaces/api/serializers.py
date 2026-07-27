from __future__ import annotations

from rest_framework import serializers


class JournalEntrySerializer(serializers.Serializer):
    correlation_id = serializers.UUIDField()
    account_id = serializers.UUIDField()
    signal_snapshot = serializers.JSONField(allow_null=True)
    decision_snapshot = serializers.JSONField(allow_null=True)
    order_events = serializers.JSONField(allow_null=True)
    position_id = serializers.UUIDField(allow_null=True)
    outcome = serializers.CharField(allow_null=True)
    realized_pnl = serializers.DecimalField(max_digits=20, decimal_places=8, allow_null=True)
    finalized = serializers.BooleanField()
    finalized_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)
