from __future__ import annotations

from django.apps import AppConfig


class WatchlistConfig(AppConfig):
    """Django AppConfig for the ``watchlist`` app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.watchlist"
    label = "watchlist"
    verbose_name = "Watchlist"
