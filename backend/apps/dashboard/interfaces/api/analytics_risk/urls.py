from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from django.urls import path

from apps.dashboard.interfaces.api.analytics_risk.views import (
    DailyRollupView,
    PerformanceView,
    PnLAnalyticsView,
    RiskSummaryView,
    DriftAlertsView,
    RuleExpectationsView,
    EdgeValidationReportView,
    ScannerStatusView,
    ScannerRuleView,
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
    path(
        "drift-alerts",
        DriftAlertsView.as_view(),
        name="drift-alerts",
    ),
    path(
        "rule-expectations",
        RuleExpectationsView.as_view(),
        name="rule-expectations",
    ),
    path(
        "edge-validation-report",
        EdgeValidationReportView.as_view(),
        name="edge-validation-report",
    ),
    path(
        "scan-status",
        ScannerStatusView.as_view(),
        name="scanner-status",
    ),
    path(
        "rules/",
        ScannerRuleView.as_view(),
        name="scanner-rules",
    ),
]
