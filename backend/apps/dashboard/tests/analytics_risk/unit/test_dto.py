from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from apps.dashboard.application.analytics_risk.dto import (
    DailyPnLPoint,
    PerformanceDTO,
    PnLSummaryDTO,
    PnLTimeSeriesPoint,
    RiskSummaryDTO,
)


class TestDTOs:
    def test_pnl_time_series_point(self) -> None:
        p = PnLTimeSeriesPoint(
            snapshot_at=datetime(2024, 1, 1, 12, 0, 0),
            realized_pnl=Decimal("100"),
            unrealized_pnl=Decimal("50"),
            total_pnl=Decimal("150"),
            cumulative_pnl=Decimal("1000"),
            drawdown_pct=Decimal("5.0"),
        )
        assert p.total_pnl == Decimal("150")

    def test_pnl_summary_dto(self) -> None:
        dto = PnLSummaryDTO(
            current_total_pnl=Decimal("500"),
            current_unrealized_pnl=Decimal("100"),
            peak_cumulative_pnl=Decimal("1000"),
            current_drawdown_pct=Decimal("10.0"),
            time_series=[],
            metadata={"period": "all_time"},
        )
        assert dto.current_total_pnl == Decimal("500")

    def test_daily_pnl_point(self) -> None:
        p = DailyPnLPoint(
            trading_date="2024-01-01",
            realized_pnl=Decimal("50"),
            total_pnl=Decimal("75"),
            cumulative_pnl=Decimal("500"),
        )
        assert p.trading_date == "2024-01-01"

    def test_performance_dto_defaults(self) -> None:
        dto = PerformanceDTO(
            period="30d",
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
        assert dto.total_trades == 0

    def test_risk_summary_dto(self) -> None:
        dto = RiskSummaryDTO(
            total_exposure=Decimal("5000"),
            largest_position_pct=Decimal("25.0"),
            sector_concentration_pct=Decimal("40.0"),
            leverage_ratio=Decimal("1.5"),
            active_alerts=[],
        )
        assert dto.leverage_ratio == Decimal("1.5")
