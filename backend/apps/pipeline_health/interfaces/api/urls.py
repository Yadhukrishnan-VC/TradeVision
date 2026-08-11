from __future__ import annotations

from django.urls import path

from apps.pipeline_health.interfaces.api.views import PipelineHealthView

app_name = "pipeline_health"

urlpatterns = [
    path("", PipelineHealthView.as_view(), name="pipeline-health"),
]
