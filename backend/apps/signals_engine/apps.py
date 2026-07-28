from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class SignalsEngineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.signals_engine"
    label = "signals_engine"
    verbose_name = "Signals Engine"

    def ready(self) -> None:
        from apps.eventbus.application.services import EventBusService

        EventBusService.register_all_handlers()
