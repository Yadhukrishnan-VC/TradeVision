from __future__ import annotations

from django.contrib import admin

from apps.trader_memory.infrastructure.models import MemoryEntry, MemoryProjection


@admin.register(MemoryEntry)
class MemoryEntryAdmin(admin.ModelAdmin):
    list_display = ("recommendation_id", "event_type", "occurred_at", "created_at")
    list_filter = ("event_type", "occurred_at")
    search_fields = ("recommendation_id", "event_type")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(MemoryProjection)
class MemoryProjectionAdmin(admin.ModelAdmin):
    list_display = ("strategy_id", "sample_size", "win_rate", "avg_confidence_at_publish", "last_recomputed_at")
    list_filter = ("last_recomputed_at",)
    search_fields = ("strategy_id",)
    readonly_fields = ("id", "created_at", "updated_at")
