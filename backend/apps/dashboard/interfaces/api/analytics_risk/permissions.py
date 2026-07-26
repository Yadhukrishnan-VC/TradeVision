from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.accounts.domain.value_objects import Scope


class HasDashboardReadPnlAnalytics(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope
        return HasAPIKeyScope.with_scope(Scope.DASHBOARD_READ_PNL_ANALYTICS).has_permission(request, view)


class HasDashboardReadPerformanceMetrics(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope
        return HasAPIKeyScope.with_scope(Scope.DASHBOARD_READ_PERFORMANCE_METRICS).has_permission(request, view)


class HasDashboardReadRisk(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope
        return HasAPIKeyScope.with_scope(Scope.DASHBOARD_READ_RISK).has_permission(request, view)
