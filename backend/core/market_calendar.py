"""
TradeVision AI — NSE market calendar.

Determines the current market session and whether a given date is a
trading day. All calculations use IST (Asia/Kolkata).

IMPORTANT: The NSE holiday list must be updated annually from the
official NSE circular (https://www.nseindia.com/). The hardcoded
dates below are correct for 2024 and 2025 at the time of writing
but are subject to last-minute changes by the exchange.
"""

import logging
from datetime import date, datetime, time
from enum import Enum
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_IST = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# Market session enum
# ---------------------------------------------------------------------------


class MarketSession(str, Enum):
    """NSE market session states."""

    PRE_MARKET = "pre_market"
    """09:00–09:15 IST — call auction / pre-open."""

    MARKET_HOURS = "market_hours"
    """09:15–15:30 IST — continuous trading session."""

    POST_MARKET = "post_market"
    """15:30–16:00 IST — closing session / post-close."""

    CLOSED = "closed"
    """Outside all sessions (evening, night, morning before 09:00)."""

    HOLIDAY = "holiday"
    """Exchange holiday or weekend."""


# ---------------------------------------------------------------------------
# NSE holiday data
# ---------------------------------------------------------------------------

# 2024 NSE equity market holidays (verified against NSE circular)
_NSE_HOLIDAYS_2024: frozenset[date] = frozenset(
    [
        date(2024, 1, 26),   # Republic Day
        date(2024, 3, 25),   # Holi
        date(2024, 4, 14),   # Dr. B.R. Ambedkar Jayanti
        date(2024, 4, 17),   # Good Friday
        date(2024, 4, 21),   # Shri Ram Navami
        date(2024, 5, 23),   # Buddha Purnima
        date(2024, 6, 17),   # Eid ul-Adha (Bakri Eid)
        date(2024, 7, 17),   # Muharram
        date(2024, 8, 15),   # Independence Day
        date(2024, 10, 2),   # Mahatma Gandhi Jayanti
        date(2024, 11, 1),   # Diwali Laxmi Pujan
        date(2024, 11, 15),  # Gurunanak Jayanti
        date(2024, 12, 25),  # Christmas Day
    ]
)

# 2025 NSE equity market holidays (provisional — verify before production)
_NSE_HOLIDAYS_2025: frozenset[date] = frozenset(
    [
        date(2025, 1, 26),   # Republic Day
        date(2025, 2, 26),   # Mahashivratri
        date(2025, 3, 14),   # Holi
        date(2025, 4, 10),   # Shri Ram Navami
        date(2025, 4, 14),   # Dr. B.R. Ambedkar Jayanti
        date(2025, 4, 18),   # Good Friday
        date(2025, 5, 12),   # Buddha Purnima
        date(2025, 6, 7),    # Eid ul-Adha (Bakri Eid)
        date(2025, 8, 15),   # Independence Day
        date(2025, 8, 27),   # Ganesh Chaturthi
        date(2025, 10, 2),   # Mahatma Gandhi Jayanti
        date(2025, 10, 21),  # Dussehra
        date(2025, 10, 23),  # Diwali Laxmi Pujan
        date(2025, 10, 24),  # Diwali Balipratipada
        date(2025, 11, 5),   # Gurunanak Jayanti
        date(2025, 12, 25),  # Christmas Day
    ]
)

_ALL_HOLIDAYS: frozenset[date] = _NSE_HOLIDAYS_2024 | _NSE_HOLIDAYS_2025


# ---------------------------------------------------------------------------
# MarketCalendar
# ---------------------------------------------------------------------------


class MarketCalendar:
    """
    NSE market session calculator.

    All session boundaries are in IST (Asia/Kolkata). Instances are
    lightweight value objects; create one per component or use the
    module-level ``get_market_calendar()`` factory for a shared instance.

    Args:
        holidays: Set of exchange holiday dates. Defaults to the bundled
                  2024–2025 NSE holiday list.
    """

    # Session boundaries (IST)
    _PRE_MARKET_START: time = time(9, 0)
    _MARKET_OPEN: time = time(9, 15)
    _MARKET_CLOSE: time = time(15, 30)
    _POST_MARKET_END: time = time(16, 0)

    def __init__(
        self,
        holidays: frozenset[date] | None = None,
    ) -> None:
        """Initialise the calendar with a set of exchange holiday dates."""
        self._holidays: frozenset[date] = holidays if holidays is not None else _ALL_HOLIDAYS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_trading_day(self, dt: date) -> bool:
        """
        Return True if ``dt`` is an NSE trading day.

        A trading day is a weekday (Mon–Fri) that is not an exchange holiday.

        Args:
            dt: The date to evaluate.
        """
        return dt.weekday() < 5 and dt not in self._holidays

    def get_session(self, dt: datetime) -> MarketSession:
        """
        Return the NSE market session for the given datetime.

        Args:
            dt: A timezone-aware datetime. Naive datetimes raise ValueError.

        Returns:
            The ``MarketSession`` corresponding to the datetime.

        Raises:
            ValueError: If ``dt`` is timezone-naive.
        """
        if dt.tzinfo is None:
            raise ValueError(
                f"get_session requires a timezone-aware datetime, got: {dt!r}"
            )

        ist_dt = dt.astimezone(_IST)
        today = ist_dt.date()

        if not self.is_trading_day(today):
            return MarketSession.HOLIDAY

        current_time = ist_dt.time().replace(second=0, microsecond=0)

        if current_time < self._PRE_MARKET_START:
            return MarketSession.CLOSED
        if current_time < self._MARKET_OPEN:
            return MarketSession.PRE_MARKET
        if current_time < self._MARKET_CLOSE:
            return MarketSession.MARKET_HOURS
        if current_time < self._POST_MARKET_END:
            return MarketSession.POST_MARKET
        return MarketSession.CLOSED

    def is_market_hours(self, dt: datetime | None = None) -> bool:
        """
        Return True if it is currently within the continuous trading session.

        Args:
            dt: Optional datetime to check. Defaults to ``now()`` in IST.
        """
        from core.utils import get_ist_now

        check_dt = dt if dt is not None else get_ist_now()
        return self.get_session(check_dt) == MarketSession.MARKET_HOURS

    def next_trading_day(self, dt: date) -> date:
        """
        Return the next NSE trading day after ``dt``.

        Skips weekends and holidays. Safe to call for any date including
        those already on a trading day.

        Args:
            dt: The reference date (result will be strictly after this date).
        """
        candidate = dt
        for _ in range(14):  # Maximum 14 days covers any holiday+weekend gap
            candidate = date(
                candidate.year,
                candidate.month,
                candidate.day,
            )
            # Add one day
            import datetime as _dt_mod
            candidate = candidate + _dt_mod.timedelta(days=1)
            if self.is_trading_day(candidate):
                return candidate

        # Fallback — should never be reached with a correct holiday list
        logger.error(
            "next_trading_day: no trading day found within 14 days",
            extra={"reference_date": str(dt)},
        )
        raise RuntimeError(f"Could not find the next trading day after {dt}")

    def seconds_to_market_open(self, dt: datetime | None = None) -> int:
        """
        Return the number of seconds until the next market open.

        Returns 0 if the market is currently in the trading session.

        Args:
            dt: Optional reference datetime. Defaults to now in IST.
        """
        import datetime as _dt_mod
        from core.utils import get_ist_now

        now_ist = (dt if dt is not None else get_ist_now()).astimezone(_IST)

        if self.is_market_hours(now_ist):
            return 0

        today = now_ist.date()

        # Find the next trading day that has a market open ahead of now
        for days_ahead in range(8):
            check_date = today + _dt_mod.timedelta(days=days_ahead)
            if not self.is_trading_day(check_date):
                continue
            next_open = datetime(
                check_date.year,
                check_date.month,
                check_date.day,
                self._MARKET_OPEN.hour,
                self._MARKET_OPEN.minute,
                tzinfo=_IST,
            )
            if next_open > now_ist:
                return int((next_open - now_ist).total_seconds())

        return 0


# ---------------------------------------------------------------------------
# Module-level shared instance
# ---------------------------------------------------------------------------

_default_calendar: MarketCalendar | None = None


def get_market_calendar() -> MarketCalendar:
    """
    Return the shared MarketCalendar instance.

    The instance is created on first call and reused thereafter. Uses the
    bundled 2024–2025 NSE holiday list. For custom holiday lists, construct
    a ``MarketCalendar`` directly.
    """
    global _default_calendar
    if _default_calendar is None:
        _default_calendar = MarketCalendar()
    return _default_calendar
