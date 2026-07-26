from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.accounts.domain.value_objects import Scope


class HasDashboardReadHome(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope
        return HasAPIKeyScope.with_scope(Scope.DASHBOARD_READ_HOME).has_permission(request, view)


class HasDashboardReadPortfolio(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope
        return HasAPIKeyScope.with_scope(Scope.DASHBOARD_READ_PORTFOLIO).has_permission(request, view)


class HasDashboardReadPositions(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope
        return HasAPIKeyScope.with_scope(Scope.DASHBOARD_READ_POSITIONS).has_permission(request, view)


class HasDashboardReadOrders(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope
        return HasAPIKeyScope.with_scope(Scope.DASHBOARD_READ_ORDERS).has_permission(request, view)


class HasDashboardReadTradeHistory(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope
        return HasAPIKeyScope.with_scope(Scope.DASHBOARD_READ_TRADE_HISTORY).has_permission(request, view)
