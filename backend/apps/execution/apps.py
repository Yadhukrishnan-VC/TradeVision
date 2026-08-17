from __future__ import annotations

from django.apps import AppConfig


class ExecutionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.execution"
    label = "execution"

    def ready(self) -> None:
        import apps.execution.checks  # noqa: F401  (registers execution checks)

        from apps.eventbus.application.services import EventBusService
        EventBusService.register_all_handlers()
