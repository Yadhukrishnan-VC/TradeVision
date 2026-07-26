from __future__ import annotations

from django.urls import path

from apps.dashboard.interfaces.api.analytics_risk.views import (
    DailyRollupView,
    PerformanceView,
    PnLAnalyticsView,
    RiskSummaryView,
)

urlpatterns = [
    path(
        "accounts/<uuid:account_id>/pnl",
        PnLAnalyticsView.as_view(),
        name="pnl-analytics",
    ),
    path(
        "accounts/<uuid:account_id>/pnl/daily",
        DailyRollupView.as_view(),
        name="pnl-daily-rollup",
    ),
    path(
        "accounts/<uuid:account_id>/performance",
        PerformanceView.as_view(),
        name="performance-metrics",
    ),
    path(
        "accounts/<uuid:account_id>/risk",
        RiskSummaryView.as_view(),
        name="risk-summary",
    ),
]
