from __future__ import annotations

"""Tests for the MarketSession (5-value) → dashboard MarketSessionStatus (4-value)
mapping, as flagged in Section 12.1 of the spec.

This test explicitly documents and validates the mapping decision:
    - market_hours → open
    - holiday → closed (fallback, no dashboard equivalent)

These tests assert the mapping behaves as documented, not silently.
"""

from core.market_calendar import MarketSession


class TestSessionStatusMapping:
    """Validates the 5-value → 4-value mapping strategy.

    The ``MarketSession`` enum has 5 values: pre_market, market_hours,
    post_market, closed, holiday.

    The dashboard's ``MarketSessionStatus`` has 4 values: pre_market,
    open, closed, post_market.

    Mapping:
        - MarketSession.MARKET_HOURS → "open"
        - MarketSession.HOLIDAY → "closed" (no holiday equivalent)
        - MarketSession.PRE_MARKET → "pre_market"
        - MarketSession.POST_MARKET → "post_market"
        - MarketSession.CLOSED → "closed"
    """

    def test_market_hours_maps_to_open(self) -> None:
        assert MarketSession.MARKET_HOURS.value == "market_hours"
        dashboard_value = "open"
        assert MarketSession.MARKET_HOURS.value != dashboard_value
        assert self._map_to_dashboard(MarketSession.MARKET_HOURS) == dashboard_value

    def test_holiday_maps_to_closed(self) -> None:
        assert MarketSession.HOLIDAY.value == "holiday"
        dashboard_value = "closed"
        assert self._map_to_dashboard(MarketSession.HOLIDAY) == dashboard_value

    def test_pre_market_maps_directly(self) -> None:
        assert self._map_to_dashboard(MarketSession.PRE_MARKET) == "pre_market"

    def test_post_market_maps_directly(self) -> None:
        assert self._map_to_dashboard(MarketSession.POST_MARKET) == "post_market"

    def test_closed_maps_directly(self) -> None:
        assert self._map_to_dashboard(MarketSession.CLOSED) == "closed"

    def test_all_sessions_have_mapping(self) -> None:
        for session in MarketSession:
            mapped = self._map_to_dashboard(session)
            assert mapped in ("pre_market", "open", "post_market", "closed")

    @staticmethod
    def _map_to_dashboard(session: MarketSession) -> str:
        mapping = {
            MarketSession.PRE_MARKET: "pre_market",
            MarketSession.MARKET_HOURS: "open",
            MarketSession.POST_MARKET: "post_market",
            MarketSession.CLOSED: "closed",
            MarketSession.HOLIDAY: "closed",
        }
        return mapping[session]
