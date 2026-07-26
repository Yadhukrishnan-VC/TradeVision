from __future__ import annotations

import uuid
from typing import Any

from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView, ListCreateAPIView, RetrieveAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.dashboard.application.trading_core.dto import ExportJobDTO
from apps.dashboard.application.trading_core.services.dashboard_home_service import (
    DashboardHomeService,
)
from apps.dashboard.application.trading_core.services.live_positions_service import (
    LivePositionsService,
)
from apps.dashboard.application.trading_core.services.open_closed_trades_service import (
    ClosedTradesService,
    OpenTradesService,
)
from apps.dashboard.application.trading_core.services.orders_service import OrdersService
from apps.dashboard.application.trading_core.services.portfolio_service import PortfolioService
from apps.dashboard.application.trading_core.services.trade_history_service import (
    TradeHistoryService,
)
from apps.dashboard.domain.trading_core.exceptions import (
    AccountSummaryNotInitialized,
    HoldingNotFound,
    OrderNotFound,
    PositionNotFound,
)
from apps.dashboard.infrastructure.trading_core.models import (
    OrderSnapshot,
    PositionSnapshot,
    TradeRecord,
)
from apps.dashboard.infrastructure.trading_core.repositories import ExportJobRepository
from apps.dashboard.interfaces.api.trading_core.filters import (
    OrderFilter,
    PositionFilter,
    TradeFilter,
)
from apps.dashboard.interfaces.api.trading_core.pagination import (
    OrderCursorPagination,
    PositionCursorPagination,
    TradeCursorPagination,
)
from apps.dashboard.interfaces.api.trading_core.permissions import (
    HasDashboardReadHome,
    HasDashboardReadOrders,
    HasDashboardReadPortfolio,
    HasDashboardReadPositions,
    HasDashboardReadTradeHistory,
)
from apps.dashboard.interfaces.api.trading_core.serializers import (
    DashboardHomeSummarySerializer,
    ExportJobSerializer,
    ExportRequestSerializer,
    HoldingSerializer,
    OrderSnapshotSerializer,
    PortfolioCompositionSerializer,
    PositionSnapshotSerializer,
    TradeRecordSerializer,
)


def _problem_detail(
    exc_type: str, title: str, status_code: int, instance: str, correlation_id: str
) -> dict[str, Any]:
    return {
        "type": f"urn:tradevision:error:{exc_type}",
        "title": title,
        "status": status_code,
        "instance": instance,
        "correlation_id": correlation_id,
    }


class DashboardHomeSummaryView(GenericAPIView):
    permission_classes = [HasDashboardReadHome]
    serializer_class = DashboardHomeSummarySerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = DashboardHomeService()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        account_id = request.user.id
        try:
            dto = self._service.get_summary(account_id)
        except AccountSummaryNotInitialized:
            return Response(
                _problem_detail(
                    "account-summary-not-initialized",
                    "Account summary not initialized yet",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                    str(getattr(request, "correlation_id", "")),
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(dto)
        return Response(serializer.data)


class PortfolioCompositionView(GenericAPIView):
    permission_classes = [HasDashboardReadPortfolio]
    serializer_class = PortfolioCompositionSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = PortfolioService()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        account_id = request.user.id
        dto = self._service.get_composition(account_id)
        serializer = self.get_serializer(dto)
        return Response(serializer.data)


class HoldingDetailView(GenericAPIView):
    permission_classes = [HasDashboardReadPortfolio]
    serializer_class = HoldingSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = PortfolioService()

    def get(self, request: Request, symbol: str, *args: Any, **kwargs: Any) -> Response:
        account_id = request.user.id
        try:
            dto = self._service.get_holding_detail(account_id, symbol)
        except HoldingNotFound:
            return Response(
                _problem_detail(
                    "holding-not-found",
                    f"Holding {symbol} not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                    str(getattr(request, "correlation_id", "")),
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(dto)
        return Response(serializer.data)


class LivePositionsListView(ListAPIView):
    permission_classes = [HasDashboardReadPositions]
    serializer_class = PositionSnapshotSerializer
    pagination_class = PositionCursorPagination
    filterset_class = PositionFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = LivePositionsService()

    def get_queryset(self) -> object:
        account_id = self.request.user.id
        return PositionSnapshot.objects.filter(account_id=account_id, is_open=True)

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            dtos = [
                self._service.to_dto(pos) for pos in page
            ]
            serializer = self.get_serializer(dtos, many=True)
            return self.get_paginated_response(serializer.data)

        dtos = [self._service.to_dto(pos) for pos in queryset]
        serializer = self.get_serializer(dtos, many=True)
        return Response(serializer.data)


class LivePositionDetailView(GenericAPIView):
    permission_classes = [HasDashboardReadPositions]
    serializer_class = PositionSnapshotSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = LivePositionsService()

    def get(self, request: Request, position_id: str, *args: Any, **kwargs: Any) -> Response:
        account_id = request.user.id
        try:
            dto = self._service.get(account_id, uuid.UUID(position_id))
        except PositionNotFound:
            return Response(
                _problem_detail(
                    "position-not-found",
                    f"Position {position_id} not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                    str(getattr(request, "correlation_id", "")),
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(dto)
        return Response(serializer.data)


class OrdersListView(ListAPIView):
    permission_classes = [HasDashboardReadOrders]
    serializer_class = OrderSnapshotSerializer
    pagination_class = OrderCursorPagination
    filterset_class = OrderFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = OrdersService()

    def get_queryset(self) -> object:
        account_id = self.request.user.id
        return OrderSnapshot.objects.filter(account_id=account_id)


class OrderDetailView(GenericAPIView):
    permission_classes = [HasDashboardReadOrders]
    serializer_class = OrderSnapshotSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = OrdersService()

    def get(self, request: Request, order_id: str, *args: Any, **kwargs: Any) -> Response:
        account_id = request.user.id
        try:
            dto = self._service.get(account_id, uuid.UUID(order_id))
        except OrderNotFound:
            return Response(
                _problem_detail(
                    "order-not-found",
                    f"Order {order_id} not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                    str(getattr(request, "correlation_id", "")),
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(dto)
        return Response(serializer.data)


class TradeHistoryListView(ListAPIView):
    permission_classes = [HasDashboardReadTradeHistory]
    serializer_class = TradeRecordSerializer
    pagination_class = TradeCursorPagination
    filterset_class = TradeFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = TradeHistoryService()

    def get_queryset(self) -> object:
        account_id = self.request.user.id
        return TradeRecord.objects.filter(account_id=account_id)


class TradeExportView(GenericAPIView):
    permission_classes = [HasDashboardReadTradeHistory]
    serializer_class = ExportJobSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = TradeHistoryService()
        self._export_repo = ExportJobRepository()

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = ExportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        account_id = request.user.id
        export_id = uuid.uuid4()
        export_format = serializer.validated_data["format"]

        self._export_repo.create(
            export_id=export_id,
            account_id=account_id,
            status="pending",
            format=export_format,
        )

        from apps.dashboard.tasks.trading_core_tasks import generate_trade_history_export
        generate_trade_history_export.delay(
            export_id=str(export_id),
            account_id=str(account_id),
            filters=serializer.validated_data,
            format=export_format,
        )

        return Response(
            ExportJobSerializer({
                "export_id": export_id,
                "status": "pending",
                "format": export_format,
                "file_url": None,
                "requested_at": None,
                "completed_at": None,
                "error_message": None,
            }).data,
            status=status.HTTP_202_ACCEPTED,
        )


class TradeExportStatusView(GenericAPIView):
    permission_classes = [HasDashboardReadTradeHistory]
    serializer_class = ExportJobSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._export_repo = ExportJobRepository()

    def get(self, request: Request, export_id: str, *args: Any, **kwargs: Any) -> Response:
        account_id = request.user.id
        try:
            job = self._export_repo.get(uuid.UUID(export_id))
        except Exception:
            return Response(
                _problem_detail(
                    "export-job-not-found",
                    f"Export job {export_id} not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                    str(getattr(request, "correlation_id", "")),
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        if str(job.account_id) != str(account_id):
            return Response(
                _problem_detail(
                    "export-job-not-found",
                    "Export job not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                    str(getattr(request, "correlation_id", "")),
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(ExportJobSerializer({
            "export_id": job.export_id,
            "status": job.status,
            "format": job.format,
            "file_url": job.file_url,
            "requested_at": job.requested_at,
            "completed_at": job.completed_at,
            "error_message": job.error_message,
        }).data)


class OpenTradesListView(ListAPIView):
    permission_classes = [HasDashboardReadPositions]
    serializer_class = PositionSnapshotSerializer
    pagination_class = PositionCursorPagination
    filterset_class = PositionFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = OpenTradesService()

    def get_queryset(self) -> object:
        account_id = self.request.user.id
        return PositionSnapshot.objects.filter(account_id=account_id, is_open=True)


class ClosedTradesListView(ListAPIView):
    permission_classes = [HasDashboardReadTradeHistory]
    serializer_class = TradeRecordSerializer
    pagination_class = TradeCursorPagination
    filterset_class = TradeFilter

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = ClosedTradesService()

    def get_queryset(self) -> object:
        account_id = self.request.user.id
        return TradeRecord.objects.filter(account_id=account_id)
