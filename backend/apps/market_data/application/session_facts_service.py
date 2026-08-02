"""
TradeVision AI — Session facts service (read-only).

Derives purely historical session facts — the opening 15-minute candle,
the previous trading day's high/low, and rolling average daily volume —
from already-persisted ``market_data`` candles.

This service is deliberately narrow and read-only: it performs no indicator
math and no writes. It exists because the deterministic trading setups
(SETUP 1-3) need these historical facts, and the Rule Engine contract forbids
I/O inside ``BaseRule.evaluate()``. The Intelligence packet-assembly step
(SETUP intake) calls this service so the facts arrive inside the
``IntelligencePacket`` where rules can read them.

Time semantics:
    All candle timestamps are stored in UTC. NSE sessions are defined in IST
    (Asia/Kolkata); this module converts IST session boundaries to UTC using
    the shared ``MarketCalendar``.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from apps.market_data.domain.entities import Candle
from apps.market_data.infrastructure.repositories import CandleRepository
from core.market_calendar import get_market_calendar
from core.services import BaseService

_IST = ZoneInfo("Asia/Kolkata")
_MINUTE_15 = "15min"
_DAY_1 = "1D"

# NSE continuous trading session boundaries (IST).
_SESSION_OPEN = time(9, 15)
_SESSION_CLOSE = time(15, 30)


class SessionFactsService(BaseService):
    """Read-only derivation of historical session facts from persisted candles."""

    def __init__(
        self,
        candle_repo: CandleRepository | None = None,
        calendar: object | None = None,
    ) -> None:
        """Initialise with an injectable candle repository and market calendar."""
        super().__init__()
        self._candle_repo = candle_repo or CandleRepository()
        self._calendar = calendar or get_market_calendar()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_opening_15m_candle(
        self,
        instrument_token: int,
        reference_dt: datetime,
    ) -> Candle | None:
        """Return the opening 15-minute candle for the session of *reference_dt*.

        Args:
            instrument_token: Numeric instrument token.
            reference_dt: Timezone-aware datetime inside the target session.

        Returns:
            The 15-minute candle that opens at 09:15 IST on the session's
            trading day, or ``None`` if unavailable.
        """
        session_day = self._session_day(reference_dt)
        if session_day is None:
            return None

        open_utc = self._ist_to_utc(session_day, _SESSION_OPEN)
        close_utc = open_utc + timedelta(minutes=15)
        candles = self._candle_repo.find_range(
            instrument_token,
            _MINUTE_15,
            open_utc,
            close_utc,
        )
        return candles[0] if candles else None

    def get_previous_day_ohlc(
        self,
        instrument_token: int,
        reference_dt: datetime,
    ) -> tuple[Decimal | None, Decimal | None]:
        """Return ``(high, low)`` of the previous trading day.

        Uses the persisted ``1D`` candle when present; otherwise aggregates the
        session's 15-minute candles.

        Args:
            instrument_token: Numeric instrument token.
            reference_dt: Timezone-aware datetime inside the current session.

        Returns:
            A ``(high, low)`` tuple, or ``(None, None)`` when unavailable.
        """
        prev_day = self._previous_trading_day(reference_dt)
        if prev_day is None:
            return (None, None)

        day_start_utc, day_end_utc = self._day_bounds_utc(prev_day)
        day_candles = self._candle_repo.find_range(
            instrument_token,
            _DAY_1,
            day_start_utc,
            day_end_utc,
        )
        if day_candles:
            return (day_candles[-1].high, day_candles[-1].low)

        intraday = self._candle_repo.find_range(
            instrument_token,
            _MINUTE_15,
            day_start_utc,
            day_end_utc,
        )
        if not intraday:
            return (None, None)
        return (
            max(c.high for c in intraday),
            min(c.low for c in intraday),
        )

    def get_avg_daily_volume(
        self,
        instrument_token: int,
        reference_dt: datetime,
        days: int = 10,
    ) -> int | None:
        """Return the average ``1D`` candle volume over the trailing *days* sessions.

        Args:
            instrument_token: Numeric instrument token.
            reference_dt: Timezone-aware datetime inside the current session.
            days: Number of trailing sessions to average (default 10).

        Returns:
            Integer average volume, or ``None`` when no day candle is available.
        """
        volumes = self._collect_day_volumes(instrument_token, reference_dt, days)
        if not volumes:
            return None
        return round(sum(volumes) / len(volumes))

    def get_avg_opening_15m_volume(
        self,
        instrument_token: int,
        reference_dt: datetime,
        days: int = 10,
    ) -> int | None:
        """Return the average opening-15m candle volume over the trailing sessions.

        Args:
            instrument_token: Numeric instrument token.
            reference_dt: Timezone-aware datetime inside the current session.
            days: Number of trailing sessions to average (default 10).

        Returns:
            Integer average volume, or ``None`` when unavailable.
        """
        volumes: list[int] = []
        for day in self._trailing_trading_days(reference_dt, days):
            candle = self._opening_15m_for_day(instrument_token, day)
            if candle is not None:
                volumes.append(candle.volume)
        if not volumes:
            return None
        return round(sum(volumes) / len(volumes))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _collect_day_volumes(
        self,
        instrument_token: int,
        reference_dt: datetime,
        days: int,
    ) -> list[int]:
        volumes: list[int] = []
        for day in self._trailing_trading_days(reference_dt, days):
            day_start_utc, day_end_utc = self._day_bounds_utc(day)
            candles = self._candle_repo.find_range(
                instrument_token,
                _DAY_1,
                day_start_utc,
                day_end_utc,
            )
            if candles:
                volumes.append(candles[-1].volume)
        return volumes

    def _opening_15m_for_day(
        self,
        instrument_token: int,
        day: date,
    ) -> Candle | None:
        open_utc = self._ist_to_utc(day, _SESSION_OPEN)
        close_utc = open_utc + timedelta(minutes=15)
        candles = self._candle_repo.find_range(
            instrument_token,
            _MINUTE_15,
            open_utc,
            close_utc,
        )
        return candles[0] if candles else None

    def _session_day(self, reference_dt: datetime) -> date | None:
        ist_dt = reference_dt.astimezone(_IST)
        if not self._calendar.is_trading_day(ist_dt.date()):
            return None
        return ist_dt.date()

    def _previous_trading_day(self, reference_dt: datetime) -> date | None:
        ist_date = reference_dt.astimezone(_IST).date()
        candidate = ist_date - timedelta(days=1)
        for _ in range(14):
            if self._calendar.is_trading_day(candidate):
                return candidate
            candidate -= timedelta(days=1)
        return None

    def _trailing_trading_days(
        self,
        reference_dt: datetime,
        days: int,
    ) -> list[date]:
        result: list[date] = []
        ist_date = reference_dt.astimezone(_IST).date()
        candidate = ist_date - timedelta(days=1)
        while len(result) < days and candidate > ist_date - timedelta(days=30):
            if self._calendar.is_trading_day(candidate):
                result.append(candidate)
            candidate -= timedelta(days=1)
        return result

    def _day_bounds_utc(self, day: date) -> tuple[datetime, datetime]:
        """Return (start, end) UTC bounds covering the full IST trading day."""
        start_utc = self._ist_to_utc(day, time(0, 0))
        end_utc = self._ist_to_utc(day + timedelta(days=1), time(0, 0))
        return start_utc, end_utc

    @staticmethod
    def _ist_to_utc(day: date, t: time) -> datetime:
        ist_dt = datetime.combine(day, t, tzinfo=_IST)
        return ist_dt.astimezone(timezone.utc)
