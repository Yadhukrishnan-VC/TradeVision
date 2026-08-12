"""PORTFOLIO-RECONCILE-1 — API URL configuration."""

from __future__ import annotations

from django.urls import path

from apps.portfolio_reconciliation.interfaces.api.views import (
    DriftRecordListView,
    DriftSummaryView,
)

app_name = "portfolio_reconciliation"

urlpatterns = [
    path(
        "drift/summary/",
        DriftSummaryView.as_view(),
        name="drift-summary",
    ),
    path(
        "drift/",
        DriftRecordListView.as_view(),
        name="drift-list",
    ),
]