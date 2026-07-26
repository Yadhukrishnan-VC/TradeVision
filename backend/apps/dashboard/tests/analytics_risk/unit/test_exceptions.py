from __future__ import annotations

from apps.dashboard.domain.analytics_risk.exceptions import (
    DateRangeTooLargeError,
    InsufficientTradeDataError,
    InvalidTimeframeError,
)


class TestExceptions:
    def test_invalid_timeframe_error(self) -> None:
        exc = InvalidTimeframeError("Invalid timeframe")
        assert str(exc) == "Invalid timeframe"

    def test_date_range_too_large_error(self) -> None:
        exc = DateRangeTooLargeError("Date range too large")
        assert str(exc) == "Date range too large"

    def test_insufficient_trade_data_error(self) -> None:
        exc = InsufficientTradeDataError("Insufficient data")
        assert str(exc) == "Insufficient data"
