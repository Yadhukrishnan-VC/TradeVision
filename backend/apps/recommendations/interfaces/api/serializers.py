from __future__ import annotations

from rest_framework import serializers


class RecommendationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    symbol = serializers.CharField()
    direction = serializers.CharField()
    confidence_score = serializers.DecimalField(max_digits=5, decimal_places=2)
    status = serializers.CharField()
    analysis_event_id = serializers.UUIDField(allow_null=True)
    strategy_id = serializers.UUIDField(allow_null=True)
    published_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()


class RecommendationActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, default="", allow_blank=True)
    changed_by = serializers.CharField(required=False, default="user", allow_blank=True)


class RecommendationExplanationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    recommendation_id = serializers.UUIDField()
    trade_explanation = serializers.CharField()
    risk_explanation = serializers.CharField()
    composed_explanation = serializers.CharField()
    created_at = serializers.DateTimeField()
