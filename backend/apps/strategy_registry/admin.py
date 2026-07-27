from __future__ import annotations

from django.contrib import admin

from apps.strategy_registry.models import TradingStrategy


@admin.register(TradingStrategy)
class TradingStrategyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "status",
        "priority",
        "symbol_filter",
        "sector_filter",
        "preferred_provider",
        "confidence_threshold",
        "risk_threshold",
    )
    list_filter = ("status", "sector_filter", "preferred_provider")
    search_fields = ("name", "symbol_filter")
    ordering = ("priority", "created_at")
