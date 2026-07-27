from __future__ import annotations

from django.apps import AppConfig


class StrategyRegistryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.strategy_registry"
    label = "strategy_registry"

    def ready(self) -> None:
        from apps.eventbus.application.services import EventBusService
        EventBusService.register_all_handlers()
