from __future__ import annotations

from rest_framework import serializers


class AuditLogEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    actor = serializers.CharField()
    action = serializers.CharField()
    target_type = serializers.CharField()
    target_id = serializers.CharField()
    metadata = serializers.JSONField()
    occurred_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()
