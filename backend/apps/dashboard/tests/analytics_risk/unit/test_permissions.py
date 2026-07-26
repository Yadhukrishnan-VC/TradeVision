from __future__ import annotations

from uuid import uuid4

from django.test import TestCase

from apps.dashboard.interfaces.api.analytics_risk.permissions import (
    HasDashboardReadPerformanceMetrics,
    HasDashboardReadPnlAnalytics,
    HasDashboardReadRisk,
)
from apps.dashboard.interfaces.api.analytics_risk.views import (
    PerformanceView,
    PnLAnalyticsView,
    RiskSummaryView,
)


class TestPnLAnalyticsPermissions(TestCase):
    def setUp(self) -> None:
        self.view = PnLAnalyticsView

    def test_view_uses_correct_permission(self) -> None:
        assert HasDashboardReadPnlAnalytics in self.view.permission_classes


class TestPerformancePermissions(TestCase):
    def setUp(self) -> None:
        self.view = PerformanceView

    def test_view_uses_correct_permission(self) -> None:
        assert HasDashboardReadPerformanceMetrics in self.view.permission_classes


class TestRiskPermissions(TestCase):
    def setUp(self) -> None:
        self.view = RiskSummaryView

    def test_view_uses_correct_permission(self) -> None:
        assert HasDashboardReadRisk in self.view.permission_classes
