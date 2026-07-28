from __future__ import annotations

from django.apps import AppConfig


class TechnicalAnalysisConfig(AppConfig):
    """AppConfig for the Technical Analysis ingestion engine.

    The ``ready()`` method registers event handlers with the event bus
    during Django startup.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.technical_analysis"
    verbose_name = "Technical Analysis"

    def ready(self) -> None:
        """Register event handlers on Django startup."""
        from apps.eventbus.application.services import EventBusService

        EventBusService.register_all_handlers()
