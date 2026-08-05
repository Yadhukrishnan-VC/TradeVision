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
)
from apps.backtesting.models import BacktestRun
from apps.backtesting.repository import BacktestRunRepository
from apps.backtesting.services import BacktestStatsService
from apps.portfolio.application.capital_service import CapitalService

_DEFAULT_INITIAL_CAPITAL = Decimal("1000000")


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
