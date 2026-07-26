from __future__ import annotations

from typing import Any

import pytest
from rest_framework.request import Request

from apps.accounts.domain.value_objects import Role, Scope
from apps.dashboard.interfaces.api.trading_core.permissions import (
    HasDashboardReadHome,
    HasDashboardReadOrders,
    HasDashboardReadPortfolio,
    HasDashboardReadPositions,
    HasDashboardReadTradeHistory,
)


def _make_request(user: Any = None, auth: Any = None) -> Request:
    from django.test.client import RequestFactory
    factory = RequestFactory()
    request = factory.get("/")
    request.user = user
    request.auth = auth
    return request


class TestHasDashboardReadHome:
    def test_has_scope(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.OWNER.value})
        auth = type("APIKey", (), {"scopes": ["dashboard:read:home"]})
        request = _make_request(user=user, auth=auth)
        assert HasDashboardReadHome().has_permission(request, None) is True

    def test_missing_scope(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.OWNER.value})
        auth = type("APIKey", (), {"scopes": ["read:portfolio"]})
        request = _make_request(user=user, auth=auth)
        assert HasDashboardReadHome().has_permission(request, None) is False

    def test_no_api_key(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.OWNER.value})
        request = _make_request(user=user, auth=None)
        assert HasDashboardReadHome().has_permission(request, None) is False

    def test_unauthenticated(self) -> None:
        user = type("User", (), {"is_authenticated": False, "role": Role.OWNER.value})
        request = _make_request(user=user)
        assert HasDashboardReadHome().has_permission(request, None) is False


class TestHasDashboardReadPortfolio:
    def test_has_scope(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.OWNER.value})
        auth = type("APIKey", (), {"scopes": ["dashboard:read:portfolio"]})
        request = _make_request(user=user, auth=auth)
        assert HasDashboardReadPortfolio().has_permission(request, None) is True


class TestHasDashboardReadPositions:
    def test_has_scope(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.OWNER.value})
        auth = type("APIKey", (), {"scopes": ["dashboard:read:positions"]})
        request = _make_request(user=user, auth=auth)
        assert HasDashboardReadPositions().has_permission(request, None) is True


class TestHasDashboardReadOrders:
    def test_has_scope(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.OWNER.value})
        auth = type("APIKey", (), {"scopes": ["dashboard:read:orders"]})
        request = _make_request(user=user, auth=auth)
        assert HasDashboardReadOrders().has_permission(request, None) is True


class TestHasDashboardReadTradeHistory:
    def test_has_scope(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.OWNER.value})
        auth = type("APIKey", (), {"scopes": ["dashboard:read:trade_history"]})
        request = _make_request(user=user, auth=auth)
        assert HasDashboardReadTradeHistory().has_permission(request, None) is True
