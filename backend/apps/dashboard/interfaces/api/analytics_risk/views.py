from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from rest_framework import status
from rest_framework.exceptions import NotFound
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

class DriftAlertsView(APIView):
    """List recent DriftAlert records for dashboard visibility."""

    permission_classes = [HasDashboardReadRisk]

    def get(self, request: Request) -> Response:
        from apps.dashboard.application.analytics_risk.services import DriftAlertService

        service = DriftAlertService()
        recent = service.list_recent_alerts(limit=50)
        active_count = service.count_active_alerts()

        return Response({
            "active_alerts_count": active_count,
            "recent_alerts": recent,
        })


class RuleExpectationsView(APIView):
    """Render reconcile_rule_expectations output for dashboard."""

    permission_classes = [HasDashboardReadRisk]

    def get(self, request: Request) -> Response:
        from uuid import UUID
        from apps.portfolio_reconciliation.infrastructure.tasks import reconcile_rule_expectations

        account_id_str = request.query_params.get("account_id")
        account_id = UUID(account_id_str) if account_id_str else None

        expectations = reconcile_rule_expectations(window_hours=24) if not account_id else             {"per_rule": [], "summary_count": 0}

        return Response({
            "per_rule": expectations.get("per_rule", []),
            "summary_count": len(expectations.get("per_rule", [])),
        })


class EdgeValidationReportView(APIView):
    """Read-only render of EDGE_VALIDATION_REPORT_V2.md summary table."""

    permission_classes = [HasDashboardReadRisk]

    def get(self, request: Request) -> Response:
        from apps.dashboard.application.analytics_risk.services import EdgeValidationReportService

        service = EdgeValidationReportService()
        summary = service.get_edge_validation_summary()

        return Response(summary)





class AccountOwnershipMixin:
    """Require the URL ``account_id`` to be the caller's own account.

    ``request.user`` is the real user for both JWT and API-key auth
    (``APIKeyAuthentication`` resolves the key to its owning user), so a
    single identity check covers both paths. Returns 404 — not 403 — so the
    existence of other accounts is not disclosed.
    """

    def _ensure_own_account(self, request: Request, account_id: UUID) -> None:
        if str(request.user.id) != str(account_id):
            raise NotFound()


class PnLAnalyticsView(AccountOwnershipMixin, APIView):
    permission_classes = [HasDashboardReadPnlAnalytics]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._service = PnLAnalyticsService()

    def get(self, request: Request, account_id: UUID) -> Response:
        self._ensure_own_account(request, account_id)
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


class DailyRollupView(AccountOwnershipMixin, APIView):
    permission_classes = [HasDashboardReadPnlAnalytics]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._service = PnLAnalyticsService()

    def get(self, request: Request, account_id: UUID) -> Response:
        self._ensure_own_account(request, account_id)
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


class PerformanceView(AccountOwnershipMixin, APIView):
    permission_classes = [HasDashboardReadPerformanceMetrics]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._service = PerformanceService()

    def get(self, request: Request, account_id: UUID) -> Response:
        self._ensure_own_account(request, account_id)
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


class RiskSummaryView(AccountOwnershipMixin, APIView):
    permission_classes = [HasDashboardReadRisk]

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._service = RiskService()

    def get(self, request: Request, account_id: UUID) -> Response:
        self._ensure_own_account(request, account_id)
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


class ScannerStatusView(APIView):
    """Basic scanner status for the frontend scanner page.

    Returns whether a Chartink scan is currently active
    (based on settings.SCAN_ID) and the scan ID value.
    """
    permission_classes = []

    def get(self, request: Request) -> Response:
        from django.conf import settings
        scan_id = getattr(settings, 'SCAN_ID', 0)
        return Response({
            "scanning": bool(scan_id),
            "scan_id": scan_id,
            "message": "Chartink scan active" if scan_id else "Scan disabled. Configure SCAN_ID to enable.",
        })


