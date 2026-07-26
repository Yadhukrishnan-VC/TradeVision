from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from apps.dashboard.application.analytics_risk.dto import PerformanceDTO
from apps.dashboard.domain.analytics_risk.value_objects import Period
from apps.dashboard.infrastructure.analytics_risk.cache import PerformanceCache
from apps.dashboard.infrastructure.analytics_risk.repositories import PerformanceSnapshotRepository


class PerformanceService:
    def __init__(
        self,
        repo: PerformanceSnapshotRepository | None = None,
        cache: PerformanceCache | None = None,
    ) -> None:
        self._repo = repo or PerformanceSnapshotRepository()
        self._cache = cache or PerformanceCache()

    def get_metrics(self, account_id: UUID, period: Period) -> PerformanceDTO:
        period_str = period.value

        cached = self._cache.get_metrics(account_id, period_str)
        if cached is not None:
            return PerformanceDTO(
                period=cached["period"],
                win_rate=Decimal(str(cached["win_rate"])),
                avg_win=Decimal(str(cached["avg_win"])),
                avg_loss=Decimal(str(cached["avg_loss"])),
                profit_factor=Decimal(str(cached["profit_factor"])) if cached.get("profit_factor") else None,
                expectancy=Decimal(str(cached["expectancy"])),
                sharpe_like_ratio=Decimal(str(cached["sharpe_like_ratio"])) if cached.get("sharpe_like_ratio") else None,
                total_trades=cached["total_trades"],
                winning_trades=cached["winning_trades"],
                losing_trades=cached["losing_trades"],
            )

        snap = self._repo.get(account_id, period_str)
        if snap is None:
            return PerformanceDTO(
                period=period_str,
                win_rate=Decimal("0"),
                avg_win=Decimal("0"),
                avg_loss=Decimal("0"),
                profit_factor=None,
                expectancy=Decimal("0"),
                sharpe_like_ratio=None,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
            )

        dto = PerformanceDTO(
            period=snap.period,
            win_rate=Decimal(str(snap.win_rate)),
            avg_win=Decimal(str(snap.avg_win)),
            avg_loss=Decimal(str(snap.avg_loss)),
            profit_factor=Decimal(str(snap.profit_factor)) if snap.profit_factor else None,
            expectancy=Decimal(str(snap.expectancy)),
            sharpe_like_ratio=Decimal(str(snap.sharpe_like_ratio)) if snap.sharpe_like_ratio else None,
            total_trades=snap.total_trades,
            winning_trades=snap.winning_trades,
            losing_trades=snap.losing_trades,
        )

        self._cache_result(account_id, period_str, dto)
        return dto

    def _cache_result(self, account_id: UUID, period: str, dto: PerformanceDTO) -> None:
        data: dict[str, Any] = {
            "period": dto.period,
            "win_rate": str(dto.win_rate),
            "avg_win": str(dto.avg_win),
            "avg_loss": str(dto.avg_loss),
            "profit_factor": str(dto.profit_factor) if dto.profit_factor else None,
            "expectancy": str(dto.expectancy),
            "sharpe_like_ratio": str(dto.sharpe_like_ratio) if dto.sharpe_like_ratio else None,
            "total_trades": dto.total_trades,
            "winning_trades": dto.winning_trades,
            "losing_trades": dto.losing_trades,
        }
        self._cache.set_metrics(account_id, period, data)
