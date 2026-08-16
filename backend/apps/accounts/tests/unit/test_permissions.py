from __future__ import annotations

from typing import Any

import pytest
from rest_framework.request import Request

from apps.accounts.domain.value_objects import Role, Scope
from apps.accounts.infrastructure.permissions import HasAPIKeyScope, IsOwnerRole, IsStaffRole


def _make_request(user: Any = None, auth: Any = None) -> Request:
    from django.test.client import RequestFactory
    factory = RequestFactory()
    request = factory.get("/")
    request.user = user
    request.auth = auth
    return request


class TestIsOwnerRole:
    def test_owner_has_permission(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.OWNER.value})
        request = _make_request(user=user)
        assert IsOwnerRole().has_permission(request, None) is True

    def test_staff_does_not_have_permission(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.STAFF.value})
        request = _make_request(user=user)
        assert IsOwnerRole().has_permission(request, None) is False

    def test_viewer_does_not_have_permission(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.VIEWER.value})
        request = _make_request(user=user)
        assert IsOwnerRole().has_permission(request, None) is False

    def test_unauthenticated_has_no_permission(self) -> None:
        user = type("User", (), {"is_authenticated": False, "role": Role.OWNER.value})
        request = _make_request(user=user)
        assert IsOwnerRole().has_permission(request, None) is False


class TestIsStaffRole:
    def test_owner_has_permission(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.OWNER.value})
        request = _make_request(user=user)
        assert IsStaffRole().has_permission(request, None) is True

    def test_staff_has_permission(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.STAFF.value})
        request = _make_request(user=user)
        assert IsStaffRole().has_permission(request, None) is True

    def test_viewer_does_not_have_permission(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.VIEWER.value})
        request = _make_request(user=user)
        assert IsStaffRole().has_permission(request, None) is False


class TestHasAPIKeyScope:
    def test_has_required_scope(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.STAFF.value})
        auth = type("APIKey", (), {"scopes": ["read:market_data"]})
        request = _make_request(user=user, auth=auth)
        perm = HasAPIKeyScope.with_scope(Scope.READ_MARKET_DATA)
        assert perm.has_permission(request, None) is True

    def test_missing_required_scope(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.STAFF.value})
        auth = type("APIKey", (), {"scopes": ["read:portfolio"]})
        request = _make_request(user=user, auth=auth)
        perm = HasAPIKeyScope.with_scope(Scope.READ_MARKET_DATA)
        assert perm.has_permission(request, None) is False

    def test_no_api_key_read_scope_allows_jwt_user(self) -> None:
        """A JWT-authenticated (non-API-key) user passes read scopes by role."""
        user = type("User", (), {"is_authenticated": True, "role": Role.STAFF.value})
        request = _make_request(user=user, auth=None)
        perm = HasAPIKeyScope.with_scope(Scope.READ_MARKET_DATA)
        assert perm.has_permission(request, None) is True

    def test_jwt_viewer_can_read_scope(self) -> None:
        """DECISION (API-WIRING-CLOSURE-1): viewers may read scope-gated data."""
        user = type("User", (), {"is_authenticated": True, "role": Role.VIEWER.value})
        request = _make_request(user=user, auth=None)
        for scope in [Scope.READ_PORTFOLIO, Scope.READ_JOURNAL, Scope.DASHBOARD_READ_RISK]:
            perm = HasAPIKeyScope.with_scope(scope)
            assert perm.has_permission(request, None) is True

    def test_jwt_viewer_cannot_manage_scope(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.VIEWER.value})
        request = _make_request(user=user, auth=None)
        perm = HasAPIKeyScope.with_scope(Scope.MANAGE_RISK_POLICY)
        assert perm.has_permission(request, None) is False

    def test_jwt_staff_can_manage_scope(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.STAFF.value})
        request = _make_request(user=user, auth=None)
        perm = HasAPIKeyScope.with_scope(Scope.MANAGE_RISK_POLICY)
        assert perm.has_permission(request, None) is True

    def test_no_scope_required_returns_true(self) -> None:
        user = type("User", (), {"is_authenticated": True, "role": Role.VIEWER.value})
        request = _make_request(user=user)
        perm = HasAPIKeyScope()
        assert perm.has_permission(request, None) is True
