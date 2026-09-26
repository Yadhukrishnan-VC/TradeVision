from __future__ import annotations

from django.urls import path

from apps.strategy_registry.interfaces.api.views import (
    StrategyDetailView,
    StrategyListView,
    StrategySymbolAffinityListView,
)

urlpatterns = [
    path("", StrategyListView.as_view(), name="strategy-list"),
    path(
        "affinities/",
        StrategySymbolAffinityListView.as_view(),
        name="strategy-symbol-affinity-list",
    ),
    path("<uuid:pk>/", StrategyDetailView.as_view(), name="strategy-detail"),
]