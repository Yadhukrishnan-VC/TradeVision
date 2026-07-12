"""
Tests for core.market_calendar — weekend, holiday, session detection.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from core.market_calendar import MarketCalendar, MarketSession

_IST = ZoneInfo("Asia/Kolkata")


class TestMarketCalendar:

    def test_weekend_is_closed(self) -> None:
        cal = MarketCalendar()
        dt = datetime(2024, 3, 9, 10, 0, tzinfo=_IST)  # Saturday — not a holiday
        session = cal.get_session(dt)
        assert session == MarketSession.HOLIDAY

    def test_weekday_midday_is_open(self) -> None:
        cal = MarketCalendar()
        dt = datetime(2024, 3, 13, 10, 30, tzinfo=_IST)
        session = cal.get_session(dt)
        assert session == MarketSession.MARKET_HOURS

    def test_pre_open_session(self) -> None:
        cal = MarketCalendar()
        dt = datetime(2024, 3, 13, 9, 5, tzinfo=_IST)
        session = cal.get_session(dt)
        assert session == MarketSession.PRE_MARKET

    def test_post_close_session(self) -> None:
        cal = MarketCalendar()
        dt = datetime(2024, 3, 13, 15, 45, tzinfo=_IST)
        session = cal.get_session(dt)
        assert session == MarketSession.POST_MARKET
