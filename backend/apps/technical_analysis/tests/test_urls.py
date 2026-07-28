from __future__ import annotations

from django.urls import include, path

urlpatterns = [
    path(
        "api/v1/technical-analysis/",
        include("apps.technical_analysis.interfaces.api.urls"),
    ),
]
