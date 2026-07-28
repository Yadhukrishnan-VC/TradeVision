from __future__ import annotations

from django.apps import AppConfig


class TraderMemoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.trader_memory"
    label = "trader_memory"

    def ready(self) -> None:
        from apps.eventbus.application.services import EventBusService
        EventBusService.register_all_handlers()
