from __future__ import annotations

from django.contrib import admin

from apps.watchlist.infrastructure.models import WatchlistEntry


@admin.register(WatchlistEntry)
class WatchlistEntryAdmin(admin.ModelAdmin):
    """Admin interface for ``WatchlistEntry``."""

    list_display = [
        "account",
        "instrument",
        "note",
        "sort_order",
        "created_at",
    ]
    list_filter = ["account", "created_at"]
    search_fields = ["account__name", "instrument__tradingsymbol", "note"]
    ordering = ["account", "sort_order", "created_at"]
    autocomplete_fields = []
