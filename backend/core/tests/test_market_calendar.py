"""
Tests for core.market_calendar — weekend, holiday, session detection.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from core.market_calendar import MarketCalendar, MarketSession

_IST = ZoneInfo("Asia/Kolkata")


class TestMarketCalendar:

    def test_weekend_is_closed(self) -> None:
        # Saturday 2024-03-16 10:00 IST
        dt = datetime(2024, 3, 16, 10, 0, tzinfo=_IST)
        session = MarketCalendar.get_session(dt)
        assert session == MarketSession.CLOSED

    def test_weekday_midday_is_open(self) -> None:
        # Wednesday 2024-03-13 10:30 IST
        dt = datetime(2024, 3, 13, 10, 30, tzinfo=_IST)
        session = MarketCalendar.get_session(dt)
        assert session == MarketSession.OPEN

    def test_pre_open_session(self) -> None:
        # Wednesday 2024-03-13 09:05 IST
        dt = datetime(2024, 3, 13, 9, 5, tzinfo=_IST)
        session = MarketCalendar.get_session(dt)
        assert session == MarketSession.PRE_OPEN

    def test_post_close_session(self) -> None:
        # Wednesday 2024-03-13 15:45 IST
        dt = datetime(2024, 3, 13, 15, 45, tzinfo=_IST)
        session = MarketCalendar.get_session(dt)
        assert session == MarketSession.POST_CLOSE
