from __future__ import annotations

from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    label = "common"

    def ready(self) -> None:
        import config.checks  # noqa: F401  (registers config.* environment/DB checks)
