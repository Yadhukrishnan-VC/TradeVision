from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum
from datetime import datetime

from django.utils import timezone

from apps.dashboard.infrastructure.analytics_risk.models import PerformanceSnapshot
from apps.dashboard.infrastructure.trading_core.models import TradeRecord
from apps.dashboard.projection.base import BaseProjectionService
from apps.dashboard.projection.internal_events import DashboardInternalEvent
from apps.eventbus.domain.events import DomainEvent


class PerformanceRollupProjector(BaseProjectionService):
    name = "performance_rollup_projector"

    def _apply(self, event: DomainEvent) -> None:
        pass

    def handle_internal(self, event: DashboardInternalEvent) -> None:
        if event.event_type == "trade_record_projected":
            self._recompute(event)

    def _recompute(self, event: DashboardInternalEvent) -> None:
        account_id = event.payload["account_id"]

        periods = {
            "7d": timezone.now() - timezone.timedelta(days=7),
            "30d": timezone.now() - timezone.timedelta(days=30),
            "90d": timezone.now() - timezone.timedelta(days=90),
        }
        for period_label, cutoff in periods.items():
            self._compute_for_period(account_id, period_label, cutoff)

    def _compute_for_period(
        self, account_id: str, period_label: str, cutoff: datetime
    ) -> None:
        trades = TradeRecord.objects.filter(
            account_id=account_id,
            closed_at__gte=cutoff,
        )

        stats = trades.aggregate(
            total=Count("trade_id"),
            winning=Count("trade_id", filter=Q(realized_pnl__gt=0)),
            losing=Count("trade_id", filter=Q(realized_pnl__lt=0)),
            total_pnl=Sum("realized_pnl"),
            avg_win=Sum("realized_pnl", filter=Q(realized_pnl__gt=0)),
            avg_loss=Sum("realized_pnl", filter=Q(realized_pnl__lt=0)),
            win_count=Count("trade_id", filter=Q(realized_pnl__gt=0)),
            loss_count=Count("trade_id", filter=Q(realized_pnl__lt=0)),
        )

        total = stats["total"] or 0
        winning = stats["winning"] or 0
        losing = stats["losing"] or 0

        if total == 0:
            PerformanceSnapshot.objects.update_or_create(
                account_id=account_id,
                period=period_label,
                defaults={
                    "win_rate": Decimal("0"),
                    "avg_win": Decimal("0"),
                    "avg_loss": Decimal("0"),
                    "profit_factor": None,
                    "expectancy": Decimal("0"),
                    "sharpe_like_ratio": None,
                    "total_trades": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                },
            )
            return

        win_rate = Decimal(str(winning)) / Decimal(str(total))

        avg_win_val = Decimal("0")
        if stats["win_count"]:
            avg_win_val = Decimal(str(stats["avg_win"] or 0)) / Decimal(str(stats["win_count"]))

        avg_loss_val = Decimal("0")
        if stats["loss_count"]:
            avg_loss_val = abs(
                Decimal(str(stats["avg_loss"] or 0)) / Decimal(str(stats["loss_count"]))
            )

        profit_factor: Decimal | None = None
        total_wins = abs(Decimal(str(stats["avg_win"] or 0)))
        total_losses = abs(Decimal(str(stats["avg_loss"] or 0)))
        if total_losses > Decimal("0"):
            profit_factor = total_wins / total_losses

        expectancy = Decimal("0")
        if total > 0:
            expectancy = Decimal(str(stats["total_pnl"] or 0)) / Decimal(str(total))

        PerformanceSnapshot.objects.update_or_create(
            account_id=account_id,
            period=period_label,
            defaults={
                "win_rate": win_rate,
                "avg_win": avg_win_val,
                "avg_loss": avg_loss_val,
                "profit_factor": profit_factor,
                "expectancy": expectancy,
                "total_trades": total,
                "winning_trades": winning,
                "losing_trades": losing,
            },
        )
