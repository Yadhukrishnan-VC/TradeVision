from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.accounts.domain.value_objects import Role, Scope


class IsOwnerRole(BasePermission):
    """Grants access only to users with the OWNER role."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role == Role.OWNER.value


class IsStaffRole(BasePermission):
    """Grants access to users with OWNER or STAFF roles."""

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in (Role.OWNER.value, Role.STAFF.value)


class HasAPIKeyScope(BasePermission):
    """Permission class that checks the API key's scopes.

    Use via the classmethod ``HasAPIKeyScope.with_scope(Scope.xxx)``
    to create a pre-configured permission instance for a DRF view.
    """

    def __init__(self, required_scope: str | None = None) -> None:
        self.required_scope = required_scope

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        if self.required_scope is None:
            return True

        api_key = getattr(request, "auth", None)
        if api_key is None:
            return False

        if not hasattr(api_key, "scopes"):
            return False

        return self.required_scope in api_key.scopes

    @classmethod
    def with_scope(cls, scope: Scope) -> HasAPIKeyScope:
        """Create a configured permission instance for the given scope.

        Args:
            scope: The Scope enum member required for access.

        Returns:
            A HasAPIKeyScope instance with the required scope set.
        """
        return cls(required_scope=scope.value)
