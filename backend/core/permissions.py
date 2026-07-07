"""
TradeVision AI — DRF permission classes.

Role hierarchy (highest to lowest):
    ADMIN      Full access; can manage rules, view AI audit logs
    TRADER     Full read + personal write (portfolio, watchlist, alerts)
    READ_ONLY  Read access to market data and public recommendations only

Views declare required permissions via ``permission_classes``. Never
check roles directly inside service or model code.
"""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

# Role constants — kept in sync with accounts.models.UserRole
_ROLE_ADMIN = "ADMIN"
_ROLE_TRADER = "TRADER"
_ROLE_READ_ONLY = "READ_ONLY"


class IsAdmin(BasePermission):
    """
    Grant access only to users with the ADMIN role.

    Use for endpoints that manage system configuration, rule thresholds,
    AI audit logs, and user management.
    """

    message = "Administrator access required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return True if the authenticated user has the ADMIN role."""
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == _ROLE_ADMIN
        )


class IsTrader(BasePermission):
    """
    Grant access to users with the TRADER or ADMIN role.

    Use for endpoints that write portfolio positions, watchlists, and
    personal alert configurations.
    """

    message = "Trader or administrator access required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return True if the authenticated user has TRADER or ADMIN role."""
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in (_ROLE_TRADER, _ROLE_ADMIN)
        )


class IsReadOnly(BasePermission):
    """
    Grant read access to any authenticated user regardless of role.

    Paired with ``IsAuthenticated`` for public market-data endpoints.
    """

    message = "Authentication required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return True for any authenticated user on safe (read) methods."""
        from rest_framework.permissions import SAFE_METHODS

        return bool(
            request.user
            and request.user.is_authenticated
            and request.method in SAFE_METHODS
        )


class IsOwnerOrAdmin(BasePermission):
    """
    Object-level permission: grant access to the resource owner or an ADMIN.

    The view must pass ``obj`` — the model instance — to ``has_object_permission``.
    The model instance must have a ``user`` or ``owner`` attribute.
    """

    message = "You do not have permission to access this resource."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Require authentication at the view level before checking object ownership."""
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: object,
    ) -> bool:
        """
        Return True if the user owns the object or has the ADMIN role.

        Checks for ``obj.user`` and ``obj.owner`` attributes in that order.
        """
        if getattr(request.user, "role", None) == _ROLE_ADMIN:
            return True

        owner = getattr(obj, "user", None) or getattr(obj, "owner", None)
        return owner is not None and owner == request.user
