from __future__ import annotations

from django.contrib import admin

from apps.ingestion.infrastructure.models import RawWebhookEvent


@admin.register(RawWebhookEvent)
class RawWebhookEventAdmin(admin.ModelAdmin):
    """Admin interface for the ``RawWebhookEvent`` model."""

    list_display = [
        "id",
        "source",
        "signature_valid",
        "processed",
        "received_at",
    ]
    list_filter = ["source", "signature_valid", "processed"]
    date_hierarchy = "received_at"
    search_fields = ["id", "source"]
    ordering = ["-received_at"]
    readonly_fields = [
        "id",
        "source",
        "raw_body",
        "headers",
        "signature_valid",
        "received_at",
        "processed",
    ]
