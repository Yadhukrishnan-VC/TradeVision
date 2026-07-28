from __future__ import annotations

from rest_framework import serializers


class MemoryEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    recommendation_id = serializers.CharField()
    event_type = serializers.CharField()
    payload = serializers.JSONField()
    occurred_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()


class MemoryProjectionSerializer(serializers.Serializer):
    strategy_id = serializers.CharField()
    sample_size = serializers.IntegerField()
    win_rate = serializers.DecimalField(max_digits=8, decimal_places=6)
    avg_confidence_at_publish = serializers.DecimalField(max_digits=5, decimal_places=2)
    last_recomputed_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
