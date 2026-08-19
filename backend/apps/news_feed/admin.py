"""NEWS-FEED-1 — Django admin."""

from __future__ import annotations

from django.contrib import admin

from apps.news_feed.infrastructure.models import NewsItem


@admin.register(NewsItem)
class NewsItemAdmin(admin.ModelAdmin):
    list_display = ("source", "headline", "published_at", "ingested_at")
    list_filter = ("source",)
    search_fields = ("headline", "source", "url")
    readonly_fields = ("id", "created_at", "updated_at", "ingested_at")
    ordering = ("-published_at",)
    date_hierarchy = "published_at"
