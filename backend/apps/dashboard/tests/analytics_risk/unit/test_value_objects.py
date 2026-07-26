from __future__ import annotations

from apps.dashboard.domain.analytics_risk.value_objects import (
    Granularity,
    PERIOD_DAYS_MAP,
    MetricType,
    Period,
    RiskLevel,
    Timeframe,
)


class TestEnums:
    def test_timeframe_values(self) -> None:
        assert Timeframe.RAW.value == "raw"
        assert Timeframe.DAILY.value == "daily"
        assert Timeframe.WEEKLY.value == "weekly"
        assert Timeframe.MONTHLY.value == "monthly"

    def test_risk_level_values(self) -> None:
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MODERATE.value == "moderate"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_metric_type_values(self) -> None:
        assert MetricType.WIN_RATE.value == "win_rate"
        assert MetricType.PROFIT_FACTOR.value == "profit_factor"
        assert MetricType.EXPECTANCY.value == "expectancy"

    def test_period_values(self) -> None:
        assert Period.SEVEN_DAYS.value == "7d"
        assert Period.THIRTY_DAYS.value == "30d"
        assert Period.NINETY_DAYS.value == "90d"
        assert Period.YTD.value == "ytd"
        assert Period.ALL_TIME.value == "all_time"

    def test_period_days_map(self) -> None:
        assert PERIOD_DAYS_MAP[Period.SEVEN_DAYS] == 7
        assert PERIOD_DAYS_MAP[Period.THIRTY_DAYS] == 30
        assert PERIOD_DAYS_MAP[Period.NINETY_DAYS] == 90
        assert PERIOD_DAYS_MAP[Period.YTD] is None
        assert PERIOD_DAYS_MAP[Period.ALL_TIME] is None

    def test_granularity_values(self) -> None:
        assert Granularity.DAILY.value == "daily"
        assert Granularity.WEEKLY.value == "weekly"
        assert Granularity.MONTHLY.value == "monthly"
