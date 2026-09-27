from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.accounts.domain.value_objects import Scope


class HasReadPortfolio(BasePermission):
    """Grants access to portfolio read endpoints (``read:portfolio``)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope

        return HasAPIKeyScope.with_scope(Scope.READ_PORTFOLIO).has_permission(request, view)


class HasManageExecution(BasePermission):
    """Grants access to the manual/paper fill endpoint (``manage:execution``)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope

        return HasAPIKeyScope.with_scope(Scope.MANAGE_EXECUTION).has_permission(request, view)


class HasManageCapital(BasePermission):
    """Grants access to the daily capital set endpoint (``manage:capital``)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope

        return HasAPIKeyScope.with_scope(Scope.MANAGE_CAPITAL).has_permission(request, view)
