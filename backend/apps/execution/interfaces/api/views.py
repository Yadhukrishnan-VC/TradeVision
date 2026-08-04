from __future__ import annotations

from django.db.models import QuerySet
from rest_framework.generics import ListAPIView, RetrieveAPIView

from apps.accounts.infrastructure.permissions import IsStaffRole
from apps.execution.infrastructure.models import ExecutionRequest, Order
from apps.execution.interfaces.api.serializers import (
    ExecutionRequestSerializer,
    OrderSerializer,
)


class ExecutionRequestListView(ListAPIView):
    """List persisted execution requests (read-only, staff)."""

    permission_classes = [IsStaffRole]
    serializer_class = ExecutionRequestSerializer

    def get_queryset(self) -> QuerySet:
        qs = ExecutionRequest.objects.all().order_by("-created_at")
        symbol = self.request.query_params.get("symbol")
        status_value = self.request.query_params.get("status")
        if symbol:
            qs = qs.filter(symbol=symbol)
        if status_value:
            qs = qs.filter(status=status_value.upper())
        return qs


class OrderListView(ListAPIView):
    """List persisted orders (read-only, staff)."""

    permission_classes = [IsStaffRole]
    serializer_class = OrderSerializer

    def get_queryset(self) -> QuerySet:
        qs = Order.objects.all().order_by("-created_at")
        symbol = self.request.query_params.get("symbol")
        status_value = self.request.query_params.get("status")
        if symbol:
            qs = qs.filter(symbol=symbol)
        if status_value:
            qs = qs.filter(status=status_value.upper())
        return qs


class OrderDetailView(RetrieveAPIView):
    """Retrieve one order with its fills (read-only, staff)."""

    permission_classes = [IsStaffRole]
    serializer_class = OrderSerializer
    queryset = Order.objects.all()
