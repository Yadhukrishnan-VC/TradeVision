from __future__ import annotations

from django.contrib import admin

from apps.rule_engine.infrastructure.models import RuleConfig, RuleExecution


@admin.register(RuleConfig)
class RuleConfigAdmin(admin.ModelAdmin):
    list_display = ("rule_id", "enabled", "severity_override", "created_at")
    list_filter = ("enabled", "created_at")
    search_fields = ("rule_id",)
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("rule_id", "enabled")}),
        ("Configuration", {"fields": ("parameters", "severity_override")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(RuleExecution)
class RuleExecutionAdmin(admin.ModelAdmin):
    list_display = ("rule_id", "symbol", "severity", "analysis_event_id", "published_event_id", "created_at")
    list_filter = ("severity", "rule_id", "created_at")
    search_fields = ("rule_id", "symbol")
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("rule_id", "symbol", "severity")}),
        ("Event", {"fields": ("analysis_event_id", "trigger_data", "published_event_id")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
