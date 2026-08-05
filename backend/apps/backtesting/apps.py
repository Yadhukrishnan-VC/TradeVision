from __future__ import annotations

from django.apps import AppConfig


class BacktestingConfig(AppConfig):
    """AppConfig for the Batch M3 Historical Replay & Backtesting Engine."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backtesting"
    verbose_name = "Backtesting"
