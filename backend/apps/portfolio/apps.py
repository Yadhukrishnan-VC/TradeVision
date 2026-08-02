from __future__ import annotations

from django.apps import AppConfig


class PortfolioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.portfolio"
    label = "portfolio"

    def ready(self) -> None:
        from apps.portfolio.infrastructure import account_signals  # noqa: F401
