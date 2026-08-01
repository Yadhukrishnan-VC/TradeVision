from __future__ import annotations

from django.contrib import admin

from apps.pattern_engine.infrastructure.models import (
    HistoricalFeatureVector,
    PatternAnalysisRun,
)


@admin.register(HistoricalFeatureVector)
class HistoricalFeatureVectorAdmin(admin.ModelAdmin):
    list_display = (
        "symbol",
        "as_of",
        "price_change_pct",
        "volume_ratio",
        "rsi_14",
        "subsequent_price_change_pct",
    )
    list_filter = ("symbol",)
    search_fields = ("symbol",)
    ordering = ("-as_of",)


@admin.register(PatternAnalysisRun)
class PatternAnalysisRunAdmin(admin.ModelAdmin):
    list_display = (
        "symbol",
        "as_of",
        "confidence_contribution",
        "historical_recommendation_accuracy",
        "match_count",
    )
    list_filter = ("symbol",)
    search_fields = ("symbol",)
    ordering = ("-as_of",)

    @admin.display(description="Matches")
    def match_count(self, obj: PatternAnalysisRun) -> int:
        return len(obj.matched_patterns or [])
