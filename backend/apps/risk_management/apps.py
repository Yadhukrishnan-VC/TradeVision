from __future__ import annotations

from django.apps import AppConfig


class RiskManagementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.risk_management"
    label = "risk_management"

    def ready(self) -> None:
        from apps.eventbus.application.services import EventBusService
        EventBusService.register_all_handlers()
