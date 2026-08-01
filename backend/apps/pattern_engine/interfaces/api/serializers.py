from __future__ import annotations

from rest_framework import serializers

from apps.pattern_engine.infrastructure.models import (
    HistoricalFeatureVector,
    PatternAnalysisRun,
)


class HistoricalFeatureVectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoricalFeatureVector
        fields = (
            "id",
            "symbol",
            "as_of",
            "features",
            "subsequent_price_change_pct",
            "subsequent_window_hours",
            "created_at",
            "updated_at",
        )


class PatternAnalysisRunSerializer(serializers.ModelSerializer):
    match_count = serializers.SerializerMethodField()

    class Meta:
        model = PatternAnalysisRun
        fields = (
            "id",
            "symbol",
            "as_of",
            "top_analogue_summary",
            "confidence_contribution",
            "historical_recommendation_accuracy",
            "matched_patterns",
            "evidence",
            "data_sufficiency_note",
            "match_count",
            "created_at",
            "updated_at",
        )

    def get_match_count(self, obj: PatternAnalysisRun) -> int:
        return len(obj.matched_patterns or [])


class PatternAnalysisRunDetailSerializer(PatternAnalysisRunSerializer):
    class Meta(PatternAnalysisRunSerializer.Meta):
        fields = PatternAnalysisRunSerializer.Meta.fields
