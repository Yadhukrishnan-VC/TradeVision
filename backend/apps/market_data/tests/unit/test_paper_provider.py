from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from apps.market_data.infrastructure.providers.paper_provider import PaperMarketDataProvider
from core.market_data.base_provider import MarketDataRequest


class TestPaperMarketDataProvider:
    def test_provider_name(self) -> None:
        provider = PaperMarketDataProvider()
        assert provider.provider_name == "paper"

    def test_validate_connection(self) -> None:
        provider = PaperMarketDataProvider()
        assert provider.validate_connection() is True

    def test_health_check(self) -> None:
        provider = PaperMarketDataProvider()
        result = provider.health_check()
        assert result["status"] == "healthy"
        assert result["provider"] == "paper"

    def test_fetch_returns_bars(self) -> None:
        provider = PaperMarketDataProvider()
        now = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)
        request = MarketDataRequest(
            symbol="RELIANCE",
            interval="15min",
            from_timestamp=now,
            to_timestamp=now + timedelta(hours=4),
        )
        response = provider.fetch(request)
        assert len(response.bars) > 0
        assert response.symbol == "RELIANCE"
        assert response.provider == "paper"
        assert response.is_complete

    def test_fetch_deterministic(self) -> None:
        provider = PaperMarketDataProvider()
        now = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)
        request = MarketDataRequest(
            symbol="TCS",
            interval="1min",
            from_timestamp=now,
            to_timestamp=now + timedelta(hours=1),
        )

        response1 = provider.fetch(request)
        response2 = provider.fetch(request)

        assert len(response1.bars) == len(response2.bars)
        for b1, b2 in zip(response1.bars, response2.bars):
            assert b1.open_price == b2.open_price
            assert b1.close_price == b2.close_price

    def test_fetch_instruments(self) -> None:
        provider = PaperMarketDataProvider()
        instruments = provider.fetch_instruments()
        assert len(instruments) == 10
        assert instruments[0]["tradingsymbol"] == "RELIANCE"
        assert instruments[0]["exchange"] == "NSE"

    def test_close_no_error(self) -> None:
        provider = PaperMarketDataProvider()
        provider.close()

    def test_ohlcv_validation(self) -> None:
        provider = PaperMarketDataProvider()
        now = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)
        request = MarketDataRequest(
            symbol="RELIANCE",
            interval="15min",
            from_timestamp=now,
            to_timestamp=now + timedelta(hours=1),
        )
        response = provider.fetch(request)

        for bar in response.bars:
            assert bar.high >= bar.low
            assert bar.volume >= 0
            assert bar.open_price > 0
