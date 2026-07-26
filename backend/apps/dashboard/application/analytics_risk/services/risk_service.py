from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from apps.dashboard.application.analytics_risk.dto import RiskSummaryDTO
from apps.dashboard.infrastructure.analytics_risk.cache import RiskLatestCache
from apps.dashboard.infrastructure.analytics_risk.repositories import RiskAlertProjectionRepository, RiskMetricSnapshotRepository
from apps.dashboard.infrastructure.trading_core.cache import LatestPriceCache


class RiskService:
    def __init__(
        self,
        metric_repo: RiskMetricSnapshotRepository | None = None,
        alert_repo: RiskAlertProjectionRepository | None = None,
        cache: RiskLatestCache | None = None,
        price_cache: LatestPriceCache | None = None,
    ) -> None:
        self._metric_repo = metric_repo or RiskMetricSnapshotRepository()
        self._alert_repo = alert_repo or RiskAlertProjectionRepository()
        self._cache = cache or RiskLatestCache()
        self._price_cache = price_cache or LatestPriceCache()

    def get_summary(self, account_id: UUID) -> RiskSummaryDTO:
        latest = self._metric_repo.get_latest(account_id)

        active_alerts = list(
            self._alert_repo.list_active(account_id).values(
                "alert_id", "alert_type", "severity", "message", "raised_at"
            )
        )

        if latest is None:
            return RiskSummaryDTO(
                total_exposure=Decimal("0"),
                largest_position_pct=Decimal("0"),
                sector_concentration_pct=Decimal("0"),
                leverage_ratio=Decimal("1"),
                active_alerts=active_alerts,
            )

        return RiskSummaryDTO(
            total_exposure=Decimal(str(latest.total_exposure)),
            largest_position_pct=Decimal(str(latest.largest_position_pct)),
            sector_concentration_pct=Decimal(str(latest.sector_concentration_pct)),
            leverage_ratio=Decimal(str(latest.leverage_ratio)),
            active_alerts=active_alerts,
        )

    def get_metric_history(
        self, account_id: UUID, date_from: datetime, date_to: datetime
    ) -> list[dict[str, object]]:
        metrics = self._metric_repo.filter_by_date_range(account_id, date_from, date_to)
        return [
            {
                "snapshot_at": m.snapshot_at.isoformat(),
                "total_exposure": str(m.total_exposure),
                "largest_position_pct": str(m.largest_position_pct),
                "sector_concentration_pct": str(m.sector_concentration_pct),
                "leverage_ratio": str(m.leverage_ratio),
            }
            for m in metrics
        ]
