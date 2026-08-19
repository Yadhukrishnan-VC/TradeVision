from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.domain.value_objects import Role
from apps.dashboard.interfaces.api.analytics_risk.views import (
    DailyRollupView,
    PerformanceView,
    PnLAnalyticsView,
    RiskSummaryView,
)

User = get_user_model()


def _create_viewer() -> User:
    user = User.objects.create_user(username="analytics-viewer", password="TestPass123!")
    user.role = Role.VIEWER.value
    user.save()
    return user


class TestPnLAnalyticsView(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = _create_viewer()
        self.account_id = self.user.id

    def _auth(self, url: str, data: dict | None = None):
        request = self.factory.get(url, data)
        force_authenticate(request, user=self.user)
        return request

    def test_get_returns_200(self) -> None:
        view = PnLAnalyticsView.as_view()
        request = self._auth(f"/api/v1/dashboard/accounts/{self.account_id}/pnl")
        response = view(request, self.account_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_with_period(self) -> None:
        view = PnLAnalyticsView.as_view()
        request = self._auth(
            f"/api/v1/dashboard/accounts/{self.account_id}/pnl",
            {"period": "30d"},
        )
        response = view(request, self.account_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_post_returns_501(self) -> None:
        view = PnLAnalyticsView.as_view()
        request = self.factory.post(f"/api/v1/dashboard/accounts/{self.account_id}/pnl")
        force_authenticate(request, user=self.user)
        response = view(request, self.account_id)
        self.assertEqual(response.status_code, status.HTTP_501_NOT_IMPLEMENTED)


class TestDailyRollupView(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = _create_viewer()
        self.account_id = self.user.id

    def _auth(self, url: str, data: dict | None = None):
        request = self.factory.get(url, data)
        force_authenticate(request, user=self.user)
        return request

    def test_get_without_dates_returns_400(self) -> None:
        view = DailyRollupView.as_view()
        request = self._auth(f"/api/v1/dashboard/accounts/{self.account_id}/pnl/daily")
        response = view(request, self.account_id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_with_dates_returns_200(self) -> None:
        view = DailyRollupView.as_view()
        request = self._auth(
            f"/api/v1/dashboard/accounts/{self.account_id}/pnl/daily",
            {"date_from": "2024-01-01", "date_to": "2024-01-31"},
        )
        response = view(request, self.account_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_get_with_invalid_dates_returns_400(self) -> None:
        view = DailyRollupView.as_view()
        request = self._auth(
            f"/api/v1/dashboard/accounts/{self.account_id}/pnl/daily",
            {"date_from": "invalid", "date_to": "2024-01-31"},
        )
        response = view(request, self.account_id)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestPerformanceView(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = _create_viewer()
        self.account_id = self.user.id

    def _auth(self, url: str, data: dict | None = None):
        request = self.factory.get(url, data)
        force_authenticate(request, user=self.user)
        return request

    def test_get_returns_200(self) -> None:
        view = PerformanceView.as_view()
        request = self._auth(f"/api/v1/dashboard/accounts/{self.account_id}/performance")
        response = view(request, self.account_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TestRiskSummaryView(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.user = _create_viewer()
        self.account_id = self.user.id

    def _auth(self, url: str, data: dict | None = None):
        request = self.factory.get(url, data)
        force_authenticate(request, user=self.user)
        return request

    def test_get_returns_200(self) -> None:
        view = RiskSummaryView.as_view()
        request = self._auth(f"/api/v1/dashboard/accounts/{self.account_id}/risk")
        response = view(request, self.account_id)
        self.assertEqual(response.status_code, status.HTTP_200_OK)