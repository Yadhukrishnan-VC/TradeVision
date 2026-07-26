from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.utils import timezone

from apps.dashboard.application.analytics_risk.dto import DailyPnLPoint, PnLSummaryDTO, PnLTimeSeriesPoint
from apps.dashboard.domain.analytics_risk.value_objects import Granularity, Period, PERIOD_DAYS_MAP
from apps.dashboard.infrastructure.analytics_risk.cache import RiskLatestCache
from apps.dashboard.infrastructure.analytics_risk.models import PnLDailyRollup, PnLSnapshot
from apps.dashboard.infrastructure.analytics_risk.repositories import PnLDailyRollupRepository, PnLSnapshotRepository
from apps.dashboard.infrastructure.trading_core.cache import LatestPriceCache


class PnLAnalyticsService:
    def __init__(
        self,
        snapshot_repo: PnLSnapshotRepository | None = None,
        rollup_repo: PnLDailyRollupRepository | None = None,
        cache: RiskLatestCache | None = None,
        price_cache: LatestPriceCache | None = None,
    ) -> None:
        self._snapshot_repo = snapshot_repo or PnLSnapshotRepository()
        self._rollup_repo = rollup_repo or PnLDailyRollupRepository()
        self._cache = cache or RiskLatestCache()
        self._price_cache = price_cache or LatestPriceCache()

    def get_summary(self, account_id: UUID, period: Period) -> PnLSummaryDTO:
        days = PERIOD_DAYS_MAP[period]
        now = timezone.now()

        if days is not None:
            date_from = now - timedelta(days=days)
        else:
            date_from = datetime(now.year, 1, 1, tzinfo=now.tzinfo) if period == Period.YTD else datetime(2000, 1, 1, tzinfo=now.tzinfo)

        snapshots = self._snapshot_repo.filter_by_date_range(account_id, date_from, now)
        latest = snapshots.first()

        time_series = [
            PnLTimeSeriesPoint(
                snapshot_at=s.snapshot_at,
                realized_pnl=Decimal(str(s.realized_pnl)),
                unrealized_pnl=Decimal(str(s.unrealized_pnl)),
                total_pnl=Decimal(str(s.total_pnl)),
                cumulative_pnl=Decimal(str(s.cumulative_pnl)),
                drawdown_pct=Decimal(str(s.drawdown_pct)),
            )
            for s in snapshots
        ]

        metadata: dict[str, Any] = {
            "period": period.value,
            "point_count": len(time_series),
        }

        if latest:
            current = Decimal(str(latest.cumulative_pnl))
            peak = Decimal(str(latest.peak_cumulative_pnl))
            drawdown = Decimal(str(latest.drawdown_pct))
            unrealized = Decimal(str(latest.unrealized_pnl))
        else:
            current = Decimal("0")
            peak = Decimal("0")
            drawdown = Decimal("0")
            unrealized = Decimal("0")

        return PnLSummaryDTO(
            current_total_pnl=current,
            current_unrealized_pnl=unrealized,
            peak_cumulative_pnl=peak,
            current_drawdown_pct=drawdown,
            time_series=time_series,
            metadata=metadata,
        )

    def get_daily_rollup(
        self, account_id: UUID, date_from: date, date_to: date
    ) -> list[DailyPnLPoint]:
        rollups = self._rollup_repo.filter_by_date_range(account_id, date_from, date_to)
        return [
            DailyPnLPoint(
                trading_date=str(r.trading_date),
                realized_pnl=Decimal(str(r.realized_pnl)),
                total_pnl=Decimal(str(r.total_pnl)),
                cumulative_pnl=Decimal(str(r.cumulative_pnl)),
            )
            for r in rollups
        ]
