from __future__ import annotations

from django.apps import AppConfig


class PatternEngineConfig(AppConfig):
    """AppConfig for the Pattern Engine (Batch AI-5).

    The ``ready()`` method registers the Pattern Engine's event handlers
    (subscribing to ``intelligence.PacketBuilt`` — the only stream that
    carries the full IntelligencePacket) with the event bus during Django
    startup — same convention as every other app.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pattern_engine"
    label = "pattern_engine"
    verbose_name = "Pattern Engine"

    def ready(self) -> None:
        from apps.eventbus.application.services import EventBusService

        EventBusService.register_all_handlers()
