from __future__ import annotations

from django.contrib import admin

from apps.recommendations.infrastructure.models import Recommendation, RecommendationStatusHistory


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ("symbol", "direction", "confidence_score", "status", "published_at", "created_at")
    list_filter = ("status", "direction", "created_at")
    search_fields = ("symbol",)
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("symbol", "direction", "confidence_score", "status")}),
        ("References", {"fields": ("analysis_event_id", "rule_execution", "strategy_id", "confidence_evaluation_id")}),
        ("Publication", {"fields": ("published_at",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(RecommendationStatusHistory)
class RecommendationStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("recommendation", "from_status", "to_status", "reason", "changed_by", "created_at")
    list_filter = ("from_status", "to_status", "created_at")
    search_fields = ("recommendation__symbol",)
    readonly_fields = ("id", "created_at", "updated_at")
