from __future__ import annotations

from django.contrib import admin

from apps.signals_engine.infrastructure.models import Signal


@admin.register(Signal)
class SignalAdmin(admin.ModelAdmin):
    list_display = (
        "instrument_symbol",
        "direction",
        "timeframe",
        "confidence_hint",
        "source_alert_id",
        "created_at",
    )
    list_filter = ("direction", "timeframe", "created_at")
    search_fields = ("instrument_symbol", "source_alert_id")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at")
