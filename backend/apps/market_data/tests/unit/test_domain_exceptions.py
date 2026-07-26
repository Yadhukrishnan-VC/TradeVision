from __future__ import annotations

from apps.common.domain.exceptions import NotFoundError
from apps.market_data.domain.exceptions import (
    StaleCandleDataError,
    UnknownInstrumentError,
    UnsupportedTimeframeError,
)


class TestDomainExceptions:
    def test_unknown_instrument_is_not_found_error(self) -> None:
        exc = UnknownInstrumentError(message="Test error")
        assert isinstance(exc, NotFoundError)
        assert str(exc) == "Test error"

    def test_unknown_instrument_with_details(self) -> None:
        exc = UnknownInstrumentError(
            message="Not found",
            details={"symbol": "RELIANCE"},
        )
        assert exc.details["symbol"] == "RELIANCE"

    def test_stale_candle_data_error(self) -> None:
        exc = StaleCandleDataError(
            message="Not enough candles",
            details={"available": 5, "needed": 50},
        )
        assert "Not enough candles" in str(exc)

    def test_unsupported_timeframe_error(self) -> None:
        exc = UnsupportedTimeframeError("Bad timeframe")
        assert "Bad timeframe" in str(exc)
