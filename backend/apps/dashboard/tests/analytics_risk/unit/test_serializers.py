from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.dashboard.interfaces.api.analytics_risk.serializers import (
    DailyRollupResponseSerializer,
    PerformanceResponseSerializer,
    PeriodQuerySerializer,
    PnLSummaryResponseSerializer,
    RiskSummaryResponseSerializer,
)


class TestPeriodQuerySerializer(TestCase):
    def test_default_period(self) -> None:
        ser = PeriodQuerySerializer(data={})
        assert ser.is_valid()
        assert ser.validated_data["period"] == "all_time"

    def test_valid_period(self) -> None:
        ser = PeriodQuerySerializer(data={"period": "30d"})
        assert ser.is_valid()
        assert ser.validated_data["period"] == "30d"

    def test_invalid_period(self) -> None:
        ser = PeriodQuerySerializer(data={"period": "invalid"})
        assert not ser.is_valid()


class TestResponseSerializers(TestCase):
    def test_pnl_summary_response(self) -> None:
        data = {
            "current_total_pnl": Decimal("500"),
            "current_unrealized_pnl": Decimal("100"),
            "peak_cumulative_pnl": Decimal("1000"),
            "current_drawdown_pct": Decimal("5.0"),
            "time_series": [],
            "metadata": {},
        }
        ser = PnLSummaryResponseSerializer(data=data)
        assert ser.is_valid(), ser.errors

    def test_daily_rollup_response(self) -> None:
        data = [
            {
                "trading_date": "2024-01-01",
                "realized_pnl": Decimal("50"),
                "total_pnl": Decimal("75"),
                "cumulative_pnl": Decimal("500"),
            }
        ]
        ser = DailyRollupResponseSerializer(data=data, many=True)
        assert ser.is_valid(), ser.errors

    def test_performance_response(self) -> None:
        data = {
            "period": "30d",
            "win_rate": Decimal("0.5"),
            "avg_win": Decimal("100"),
            "avg_loss": Decimal("50"),
            "profit_factor": Decimal("2.0"),
            "expectancy": Decimal("25"),
            "sharpe_like_ratio": Decimal("1.5"),
            "total_trades": 10,
            "winning_trades": 5,
            "losing_trades": 5,
        }
        ser = PerformanceResponseSerializer(data=data)
        assert ser.is_valid(), ser.errors

    def test_performance_response_nullable(self) -> None:
        data = {
            "period": "30d",
            "win_rate": Decimal("0"),
            "avg_win": Decimal("0"),
            "avg_loss": Decimal("0"),
            "profit_factor": None,
            "expectancy": Decimal("0"),
            "sharpe_like_ratio": None,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
        }
        ser = PerformanceResponseSerializer(data=data)
        assert ser.is_valid(), ser.errors

    def test_risk_summary_response(self) -> None:
        data = {
            "total_exposure": Decimal("5000"),
            "largest_position_pct": Decimal("25.0"),
            "sector_concentration_pct": Decimal("40.0"),
            "leverage_ratio": Decimal("1.5"),
            "active_alerts": [],
        }
        ser = RiskSummaryResponseSerializer(data=data)
        assert ser.is_valid(), ser.errors
