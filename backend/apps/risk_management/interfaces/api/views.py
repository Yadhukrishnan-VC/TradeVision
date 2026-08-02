from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.risk_management.application.kill_switch_service import KillSwitchService
from apps.risk_management.infrastructure.models import KillSwitchState
from apps.risk_management.infrastructure.repositories import RiskDecisionRepository
from apps.risk_management.interfaces.api.permissions import (
    HasDashboardReadRisk,
    HasManageRiskPolicy,
)
from apps.risk_management.interfaces.api.serializers import (
    KillSwitchStateSerializer,
    KillSwitchToggleSerializer,
    RiskDecisionSerializer,
)


def _problem_detail(
    exc_type: str, title: str, status_code: int, instance: str
) -> dict[str, Any]:
    return {
        "type": f"urn:tradevision:error:{exc_type}",
        "title": title,
        "status": status_code,
        "instance": instance,
    }


class RiskDecisionListView(ListAPIView):
    """List persisted risk decisions (read-only)."""

    permission_classes = [HasDashboardReadRisk]
    serializer_class = RiskDecisionSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._repository = RiskDecisionRepository()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        filters: dict[str, Any] = {}
        rule_id = request.query_params.get("rule_id")
        symbol = request.query_params.get("symbol")
        status_value = request.query_params.get("status")
        if rule_id:
            filters["rule_id"] = rule_id
        if symbol:
            filters["symbol"] = symbol
        if status_value:
            filters["status"] = status_value.upper()
        decisions = self._repository.list(**filters)
        serializer = self.get_serializer(decisions, many=True)
        return Response(serializer.data)


class KillSwitchListView(ListAPIView):
    """List kill-switch state history (read-only, MANAGE_RISK_POLICY)."""

    permission_classes = [HasManageRiskPolicy]
    serializer_class = KillSwitchStateSerializer

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        rows = KillSwitchState.objects.filter(
            scope=request.query_params.get("scope", ""),
            is_active=True,
        ) if request.query_params.get("scope") else KillSwitchState.objects.filter(is_active=True)
        serializer = self.get_serializer(rows, many=True)
        return Response(serializer.data)


class KillSwitchActivateView(GenericAPIView):
    """Activate a kill-switch scope (MANAGE_RISK_POLICY)."""

    permission_classes = [HasManageRiskPolicy]
    serializer_class = KillSwitchToggleSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = KillSwitchService()

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = KillSwitchToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            state = self._service.activate(
                scope=data["scope"],
                symbol=data.get("symbol") or None,
                reason=data.get("reason", ""),
                actor=getattr(request.user, "email", "system"),
            )
        except ValueError as exc:
            return Response(
                _problem_detail(
                    "invalid-kill-switch-toggle",
                    str(exc),
                    status.HTTP_400_BAD_REQUEST,
                    request.path,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        out = KillSwitchStateSerializer(state)
        return Response(out.data, status=status.HTTP_201_CREATED)


class KillSwitchDeactivateView(GenericAPIView):
    """Deactivate a kill-switch scope (MANAGE_RISK_POLICY)."""

    permission_classes = [HasManageRiskPolicy]
    serializer_class = KillSwitchToggleSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = KillSwitchService()

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = KillSwitchToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            deactivated = self._service.deactivate(
                scope=data["scope"],
                symbol=data.get("symbol") or None,
                reason=data.get("reason", ""),
                actor=getattr(request.user, "email", "system"),
            )
        except ValueError as exc:
            return Response(
                _problem_detail(
                    "invalid-kill-switch-toggle",
                    str(exc),
                    status.HTTP_400_BAD_REQUEST,
                    request.path,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not deactivated:
            return Response(
                _problem_detail(
                    "kill-switch-not-active",
                    "Kill switch was not active for the given scope",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
