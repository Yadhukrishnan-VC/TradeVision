from __future__ import annotations

from django.urls import path

from apps.pattern_engine.interfaces.api.views import (
    HistoricalFeatureVectorListView,
    PatternAnalysisRunDetailView,
    PatternAnalysisRunListView,
)

app_name = "pattern_engine"

urlpatterns = [
    path(
        "historical-vectors/",
        HistoricalFeatureVectorListView.as_view(),
        name="historical-vectors-list",
    ),
    path(
        "runs/",
        PatternAnalysisRunListView.as_view(),
        name="runs-list",
    ),
    path(
        "runs/<uuid:run_id>/",
        PatternAnalysisRunDetailView.as_view(),
        name="runs-detail",
    ),
]
