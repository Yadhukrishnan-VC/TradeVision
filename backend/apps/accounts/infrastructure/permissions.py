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

        auth = getattr(request, "auth", None)

        # Programmatic access — an API key must carry the required scope.
        if auth is not None and hasattr(auth, "scopes"):
            return self.required_scope in auth.scopes

        # Interactive access (JWT Bearer) — authorize by role.
        # DECISION (API-WIRING-CLOSURE-1, confirmed by owner): any authenticated
        # user may read scope-gated data; read:/dashboard:read: scopes are open
        # to all authenticated users (matching DEFAULT_PERMISSION_CLASSES and
        # the journal's IsAuthenticated behavior). manage: scopes are reserved
        # for owner/staff. API keys still require their exact scope regardless
        # of the caller's role.
        if self.required_scope.startswith("manage:"):
            return request.user.role in (Role.OWNER.value, Role.STAFF.value)
        return True

    @classmethod
    def with_scope(cls, scope: Scope) -> HasAPIKeyScope:
        """Create a configured permission instance for the given scope.

        Args:
            scope: The Scope enum member required for access.

        Returns:
            A HasAPIKeyScope instance with the required scope set.
        """
        return cls(required_scope=scope.value)
