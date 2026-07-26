from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard.application.analytics_risk.services import PnLAnalyticsService, PerformanceService, RiskService
from apps.dashboard.domain.analytics_risk.value_objects import Period
from apps.dashboard.interfaces.api.analytics_risk.permissions import (
    HasDashboardReadPerformanceMetrics,
    HasDashboardReadPnlAnalytics,
    HasDashboardReadRisk,
)
from apps.dashboard.interfaces.api.analytics_risk.serializers import (
    DailyRollupResponseSerializer,
    PerformanceResponseSerializer,
    PeriodQuerySerializer,
    PnLSummaryResponseSerializer,
    RiskSummaryResponseSerializer,
)


class PnLAnalyticsView(APIView):
    permission_classes = [HasDashboardReadPnlAnalytics]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._service = PnLAnalyticsService()

    def get(self, request: Request, account_id: UUID) -> Response:
        query_ser = PeriodQuerySerializer(data=request.query_params)
        if not query_ser.is_valid():
            return Response(query_ser.errors, status=status.HTTP_400_BAD_REQUEST)

        period = Period(query_ser.validated_data["period"])
        summary = self._service.get_summary(account_id, period)
        ser = PnLSummaryResponseSerializer(
            {
                "current_total_pnl": summary.current_total_pnl,
                "current_unrealized_pnl": summary.current_unrealized_pnl,
                "peak_cumulative_pnl": summary.peak_cumulative_pnl,
                "current_drawdown_pct": summary.current_drawdown_pct,
                "time_series": [
                    {
                        "snapshot_at": p.snapshot_at.isoformat(),
                        "realized_pnl": p.realized_pnl,
                        "unrealized_pnl": p.unrealized_pnl,
                        "total_pnl": p.total_pnl,
                        "cumulative_pnl": p.cumulative_pnl,
                        "drawdown_pct": p.drawdown_pct,
                    }
                    for p in summary.time_series
                ],
                "metadata": summary.metadata,
            }
        )
        return Response(ser.data)

    def post(self, request: Request, account_id: UUID) -> Response:
        return Response({"error": "Not implemented"}, status=status.HTTP_501_NOT_IMPLEMENTED)


class DailyRollupView(APIView):
    permission_classes = [HasDashboardReadPnlAnalytics]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._service = PnLAnalyticsService()

    def get(self, request: Request, account_id: UUID) -> Response:
        date_from_str = request.query_params.get("date_from")
        date_to_str = request.query_params.get("date_to")

        if not date_from_str or not date_to_str:
            return Response(
                {"error": "date_from and date_to query params required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            date_from = date.fromisoformat(date_from_str)
            date_to = date.fromisoformat(date_to_str)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        rollups = self._service.get_daily_rollup(account_id, date_from, date_to)
        ser = DailyRollupResponseSerializer(
            [
                {
                    "trading_date": r.trading_date,
                    "realized_pnl": r.realized_pnl,
                    "total_pnl": r.total_pnl,
                    "cumulative_pnl": r.cumulative_pnl,
                }
                for r in rollups
            ],
            many=True,
        )
        return Response(ser.data)


class PerformanceView(APIView):
    permission_classes = [HasDashboardReadPerformanceMetrics]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._service = PerformanceService()

    def get(self, request: Request, account_id: UUID) -> Response:
        query_ser = PeriodQuerySerializer(data=request.query_params)
        if not query_ser.is_valid():
            return Response(query_ser.errors, status=status.HTTP_400_BAD_REQUEST)

        period = Period(query_ser.validated_data["period"])
        metrics = self._service.get_metrics(account_id, period)
        ser = PerformanceResponseSerializer(
            {
                "period": metrics.period,
                "win_rate": metrics.win_rate,
                "avg_win": metrics.avg_win,
                "avg_loss": metrics.avg_loss,
                "profit_factor": metrics.profit_factor,
                "expectancy": metrics.expectancy,
                "sharpe_like_ratio": metrics.sharpe_like_ratio,
                "total_trades": metrics.total_trades,
                "winning_trades": metrics.winning_trades,
                "losing_trades": metrics.losing_trades,
            }
        )
        return Response(ser.data)


class RiskSummaryView(APIView):
    permission_classes = [HasDashboardReadRisk]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._service = RiskService()

    def get(self, request: Request, account_id: UUID) -> Response:
        summary = self._service.get_summary(account_id)
        ser = RiskSummaryResponseSerializer(
            {
                "total_exposure": summary.total_exposure,
                "largest_position_pct": summary.largest_position_pct,
                "sector_concentration_pct": summary.sector_concentration_pct,
                "leverage_ratio": summary.leverage_ratio,
                "active_alerts": summary.active_alerts,
            }
        )
        return Response(ser.data)
