from __future__ import annotations

from django.apps import AppConfig


class PipelineHealthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.pipeline_health"
    label = "pipeline_health"
    verbose_name = "Pipeline Health"

    def ready(self) -> None:
        from apps.pipeline_health.infrastructure.event_consumers import (
            register_consumers,
        )

        register_consumers()
