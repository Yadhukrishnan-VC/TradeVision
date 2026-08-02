"""Unit tests for the read-only SessionFactsService.

Uses an in-memory candle repo so no DB is required. Verifies session-aware
opening-15m lookups, previous-day H/L (day-candle and 15m fallback), and
rolling average volumes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from apps.market_data.application.session_facts_service import SessionFactsService
from apps.market_data.domain.entities import Candle
from core.market_calendar import MarketCalendar

_TOKEN = 1001


class FakeCandleRepo:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def find_range(self, instrument_token, timeframe, from_timestamp, to_timestamp):
        return [
            c
            for c in self._candles
            if c.instrument_token == instrument_token
            and c.timeframe == timeframe
            and from_timestamp <= c.timestamp <= to_timestamp
        ]


def _candle(
    timeframe: str,
    ts: datetime,
    open: str = "100",
    high: str = "105",
    low: str = "99",
    close: str = "103",
    volume: int = 1_000_000,
) -> Candle:
    return Candle(
        instrument_token=_TOKEN,
        timeframe=timeframe,
        timestamp=ts,
        open=Decimal(open),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=volume,
    )


# A trading day (Monday). Session open 09:15 IST == 03:45 UTC.
_D1 = datetime(2026, 7, 27, 3, 45, tzinfo=timezone.utc)  # Mon
_D0 = datetime(2026, 7, 28, 3, 45, tzinfo=timezone.utc)  # Tue


def _calendar() -> MarketCalendar:
    return MarketCalendar(holidays=frozenset())


def _service(candles: list[Candle]) -> SessionFactsService:
    return SessionFactsService(
        candle_repo=FakeCandleRepo(candles),
        calendar=_calendar(),
    )


class TestGetOpening15mCandle:
    def test_returns_opening_candle(self) -> None:
        service = _service(
            [
                _candle("15min", _D0),
                _candle("15min", datetime(2026, 7, 28, 4, 0, tzinfo=timezone.utc)),
            ]
        )
        candle = service.get_opening_15m_candle(_TOKEN, _D0)
        assert candle is not None
        assert candle.timestamp == _D0
        assert candle.open == Decimal(100)

    def test_returns_none_when_no_candle(self) -> None:
        service = _service([])
        assert service.get_opening_15m_candle(_TOKEN, _D0) is None

    def test_returns_none_on_non_trading_day(self) -> None:
        service = _service([_candle("15min", _D0)])
        sunday = datetime(2026, 7, 26, 4, 0, tzinfo=timezone.utc)
        assert service.get_opening_15m_candle(_TOKEN, sunday) is None


class TestGetPreviousDayOhlc:
    def test_uses_day_candle(self) -> None:
        service = _service(
            [
                _candle("1D", _D1, open="90", high="98", low="88", close="95"),
                _candle("15min", _D1),
            ]
        )
        high, low = service.get_previous_day_ohlc(_TOKEN, _D0)
        assert high == Decimal(98)
        assert low == Decimal(88)

    def test_falls_back_to_15m_aggregation(self) -> None:
        service = _service(
            [
                _candle("15min", _D1, high="100", low="90"),
                _candle(
                    "15min",
                    datetime(2026, 7, 27, 4, 0, tzinfo=timezone.utc),
                    high="99",
                    low="91",
                ),
            ]
        )
        high, low = service.get_previous_day_ohlc(_TOKEN, _D0)
        assert high == Decimal(100)
        assert low == Decimal(90)

    def test_returns_none_when_no_previous_day_data(self) -> None:
        service = _service([])
        assert service.get_previous_day_ohlc(_TOKEN, _D0) == (None, None)


class TestGetAvgDailyVolume:
    def test_averages_trailing_day_volumes(self) -> None:
        service = _service(
            [
                _candle("1D", _D1, volume=1_000_000),
                _candle("1D", _D0, volume=2_000_000),
            ]
        )
        # Reference day is Tuesday (D0); trailing sessions exclude the current
        # session, so only Monday's (D1) volume is averaged.
        avg = service.get_avg_daily_volume(_TOKEN, _D0, days=10)
        assert avg is not None
        assert avg == 1_000_000

    def test_returns_none_when_no_day_candles(self) -> None:
        service = _service([])
        assert service.get_avg_daily_volume(_TOKEN, _D0, days=10) is None


class TestGetAvgOpening15mVolume:
    def test_averages_opening_candles(self) -> None:
        service = _service(
            [
                _candle("15min", _D1, volume=100_000),
                _candle("15min", _D0, volume=300_000),
            ]
        )
        avg = service.get_avg_opening_15m_volume(_TOKEN, _D0, days=10)
        assert avg is not None
        assert avg == 100_000

    def test_returns_none_when_no_opening_candles(self) -> None:
        service = _service([])
        assert service.get_avg_opening_15m_volume(_TOKEN, _D0, days=10) is None
