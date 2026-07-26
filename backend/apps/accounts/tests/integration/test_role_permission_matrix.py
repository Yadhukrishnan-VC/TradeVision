from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.domain.value_objects import Role
from apps.accounts.infrastructure.permissions import IsOwnerRole, IsStaffRole

pytestmark = pytest.mark.django_db

User = get_user_model()


class TestRolePermissionMatrix:
    """Parametrized test asserting every (role × permission-class) combination."""

    @pytest.fixture
    def api_client(self) -> APIClient:
        return APIClient()

    def _make_user(self, role: str) -> Any:
        return User.objects.create_user(
            username=f"{role}_user",
            password="TestPass123!",
            role=role,
        )

    def test_is_owner_role_only_for_owner(self) -> None:
        owner = self._make_user(Role.OWNER.value)
        staff = self._make_user(Role.STAFF.value)
        viewer = self._make_user(Role.VIEWER.value)

        for user in [owner]:
            user.is_authenticated = True  # type: ignore[attr-defined]
            assert IsOwnerRole().has_permission(
                self._make_request(user), None
            ) is True

        for user in [staff, viewer]:
            user.is_authenticated = True  # type: ignore[attr-defined]
            assert IsOwnerRole().has_permission(
                self._make_request(user), None
            ) is False

    def test_is_staff_role_for_owner_and_staff(self) -> None:
        owner = self._make_user(Role.OWNER.value)
        staff = self._make_user(Role.STAFF.value)
        viewer = self._make_user(Role.VIEWER.value)

        for user in [owner, staff]:
            user.is_authenticated = True  # type: ignore[attr-defined]
            assert IsStaffRole().has_permission(
                self._make_request(user), None
            ) is True

        viewer.is_authenticated = True  # type: ignore[attr-defined]
        assert IsStaffRole().has_permission(
            self._make_request(viewer), None
        ) is False

    def _make_request(self, user: Any) -> Any:
        class FakeRequest:
            user = user
            auth = None
            META = {}
            method = "GET"

        return FakeRequest()
