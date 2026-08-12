from __future__ import annotations

from django.apps import AppConfig


class PortfolioReconciliationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.portfolio_reconciliation"
    label = "portfolio_reconciliation"
    verbose_name = "Portfolio Reconciliation"

    def ready(self) -> None:
        # Ensure the app's models are registered with the app registry so
        # ``makemigrations``/``migrate`` see them (the models live under
        # ``infrastructure/models.py`` — the same convention as
        # ``apps.pipeline_health``, which registers its models through its
        # own ``ready()`` import chain). ``ready()`` is invoked during
        # ``django.setup()`` before management commands run.
        from apps.portfolio_reconciliation.infrastructure import models  # noqa: F401