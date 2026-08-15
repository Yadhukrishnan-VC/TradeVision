"""Batch M3 — Backtest run API views.

POST creates a ``BacktestRun`` plus its dedicated, isolated account
(``is_default=False``, funded via the existing ``CapitalService.deposit`` —
no new capital logic) and enqueues ``run_backtest`` on the analytics queue.
GET returns the run's status plus read-only per-account statistics.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from rest_framework import status as http_status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.infrastructure.models import Account
from apps.backtesting.interfaces.api.serializers import (
    BacktestRunCreateSerializer,
    BacktestRunStatsSerializer,
    CostSensitivitySerializer,
    WalkForwardSerializer,
)
from apps.backtesting.models import BacktestRun
from apps.backtesting.repository import BacktestRunRepository
from apps.backtesting.services import BacktestStatsService
from apps.portfolio.application.capital_service import CapitalService

_DEFAULT_INITIAL_CAPITAL = Decimal(1000000)
_DEFAULT_IN_SAMPLE_RATIO = Decimal("0.70")


class BacktestRunListCreateView(APIView):
    """Create and enqueue a new backtest run."""

    def post(self, request) -> Response:
        serializer = BacktestRunCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            account = Account.objects.create(
                name=f"Backtest {data['symbol']} {data['range_start'].date()}",
                owner=request.user,
                is_default=False,
            )
            CapitalService().deposit(
                account.id,
                data.get("initial_capital", _DEFAULT_INITIAL_CAPITAL),
            )
            run = BacktestRun(
                symbol=data["symbol"].upper(),
                timeframe=data.get("timeframe", ""),
                range_start=data["range_start"],
                range_end=data["range_end"],
                account=account,
                status="PENDING",
            )
            run.full_clean()
            run.save()

        from apps.backtesting.infrastructure.tasks import run_backtest

        run_backtest.delay(str(run.id))

        return Response(
            {
                "run_id": str(run.id),
                "account_id": str(account.id),
                "status": run.status,
                "symbol": run.symbol,
                "timeframe": run.timeframe,
                "range_start": run.range_start.isoformat(),
                "range_end": run.range_end.isoformat(),
            },
            status=http_status.HTTP_201_CREATED,
        )


class BacktestRunDetailView(APIView):
    """Return one run's status and read-only statistics."""

    def get(self, request, run_id: uuid.UUID) -> Response:
        run = BacktestRunRepository().get_by_id(run_id)
        if run is None:
            return Response(
                {"detail": "BacktestRun not found"},
                status=http_status.HTTP_404_NOT_FOUND,
            )
        stats = BacktestStatsService().run_stats(run)
        payload = BacktestRunStatsSerializer(run).data
        payload["stats"] = stats
        return Response(payload, status=http_status.HTTP_200_OK)


class WalkForwardView(APIView):
    """Validate a strategy walk-forward and return the OOS distribution.

    Runs synchronously: each window's ``BacktestRunnerService.run`` requires
    ``CELERY_TASK_ALWAYS_EAGER=True`` (the simulation contextvars do not cross
    Celery worker processes), so the response carries the full aggregate.
    """

    def post(self, request) -> Response:
        serializer = WalkForwardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from apps.backtesting.application.walk_forward_service import WalkForwardService

        result = WalkForwardService().execute(
            owner=request.user,
            symbol=data["symbol"].upper(),
            timeframe=data.get("timeframe", ""),
            range_start=data["range_start"],
            range_end=data["range_end"],
            window_size_days=data["window_size_days"],
            step_size_days=data["step_size_days"],
            in_sample_ratio=data.get("in_sample_ratio", _DEFAULT_IN_SAMPLE_RATIO),
            initial_capital=data.get("initial_capital", _DEFAULT_INITIAL_CAPITAL),
        )
        return Response(result, status=http_status.HTTP_200_OK)


class CostSensitivityView(APIView):
    """Sweep a cost grid and report each rule's commission/slippage breakeven.

    Purely analytical: runs the unmodified backtest engine once per grid point
    over isolated accounts and aggregates the resulting ``by_rule`` expectancies.
    Like ``WalkForwardView``, this runs synchronously and therefore requires
    ``CELERY_TASK_ALWAYS_EAGER=True`` for the simulated-time contextvars.
    """

    def post(self, request) -> Response:
        serializer = CostSensitivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from apps.backtesting.application.cost_sensitivity_service import (
            CostSensitivityService,
        )

        result = CostSensitivityService().execute(
            owner=request.user,
            symbol=data["symbol"].upper(),
            timeframe=data.get("timeframe", ""),
            range_start=data["range_start"],
            range_end=data["range_end"],
            commission_range=(data["commission_start"], data["commission_end"]),
            commission_step=data["commission_step"],
            slippage_range=(data["slippage_start"], data["slippage_end"]),
            slippage_step=data["slippage_step"],
            initial_capital=data.get("initial_capital", _DEFAULT_INITIAL_CAPITAL),
        )
        return Response(result, status=http_status.HTTP_200_OK)
