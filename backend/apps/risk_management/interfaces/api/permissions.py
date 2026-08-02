from __future__ import annotations

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.accounts.domain.value_objects import Scope


class HasDashboardReadRisk(BasePermission):
    """Grants access to risk decision reads (``dashboard:read:risk``)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope

        return HasAPIKeyScope.with_scope(Scope.DASHBOARD_READ_RISK).has_permission(request, view)


class HasManageRiskPolicy(BasePermission):
    """Grants access to kill-switch toggles (``manage:risk_policy``)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        from apps.accounts.infrastructure.permissions import HasAPIKeyScope

        return HasAPIKeyScope.with_scope(Scope.MANAGE_RISK_POLICY).has_permission(request, view)
