from __future__ import annotations

from django.apps import AppConfig


class ExecutionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.execution"
    label = "execution"

    def ready(self) -> None:
        from apps.eventbus.application.services import EventBusService
        EventBusService.register_all_handlers()
