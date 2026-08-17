"""NEWS-FEED-1 — Django app config."""

from __future__ import annotations

from django.apps import AppConfig


class NewsFeedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.news_feed"
    label = "news_feed"
    verbose_name = "News Feed"

    def ready(self) -> None:
        # Register event handlers the news feed contributes (audit auto-records
        # the news.NewsIngested events we publish; keep registration explicit).
        from apps.eventbus.application.services import EventBusService

        EventBusService.register_all_handlers()
