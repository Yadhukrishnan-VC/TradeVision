from __future__ import annotations

from rest_framework import serializers


class RuleConfigSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    rule_id = serializers.CharField()
    enabled = serializers.BooleanField()
    parameters = serializers.JSONField()
    severity_override = serializers.CharField(allow_null=True, allow_blank=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class RuleConfigUpdateSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    parameters = serializers.JSONField(required=False)
    severity_override = serializers.CharField(allow_null=True, allow_blank=True, required=False)


class RuleExecutionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    analysis_event_id = serializers.UUIDField()
    rule_id = serializers.CharField()
    symbol = serializers.CharField()
    severity = serializers.CharField()
    trigger_data = serializers.JSONField()
    published_event_id = serializers.UUIDField(allow_null=True)
    created_at = serializers.DateTimeField()
