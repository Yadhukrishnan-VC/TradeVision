from __future__ import annotations

from django.contrib import admin

from apps.journal.infrastructure.models import JournalEntry


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ("id", "correlation_id", "account", "outcome", "finalized", "realized_pnl", "created_at")
    list_filter = ("finalized", "outcome", "created_at")
    search_fields = ("correlation_id", "account__name")
    readonly_fields = ("id", "correlation_id", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("correlation_id", "account")}),
        ("Snapshots", {"fields": ("signal_snapshot", "decision_snapshot", "order_events")}),
        ("Position", {"fields": ("position_id",)}),
        ("Outcome", {"fields": ("outcome", "realized_pnl", "finalized", "finalized_at")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
