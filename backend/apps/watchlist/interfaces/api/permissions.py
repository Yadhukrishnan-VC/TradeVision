from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.accounts.domain.value_objects import Scope


class HasReadWatchlist(BasePermission):
    """Grants access to watchlist read endpoints (``read:watchlist``)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope

        return HasAPIKeyScope.with_scope(Scope.READ_WATCHLIST).has_permission(request, view)


class HasManageWatchlist(BasePermission):
    """Grants access to watchlist write endpoints (``manage:watchlist``)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope

        return HasAPIKeyScope.with_scope(Scope.MANAGE_WATCHLIST).has_permission(request, view)


class IsWatchlistAccountOwner(BasePermission):
    """Server-side account ownership check.

    Rejects with 403 (never 404, which would leak account existence) when the
    referenced account is not owned by the caller. The account id is resolved
    from the query string (GET/DELETE) or the request body (POST/PATCH).
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False

        account_id = self._resolve_account_id(request)
        if account_id is None:
            return True  # missing id is a validation error, not an ownership one

        from apps.accounts.infrastructure.models import Account

        try:
            return Account.objects.filter(id=account_id, owner=request.user).exists()
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _resolve_account_id(request: Request) -> Any:
        if request.method in ("POST", "PATCH"):
            if getattr(request, "data", None):
                return request.data.get("account_id")
            return None
        return request.query_params.get("account_id")
