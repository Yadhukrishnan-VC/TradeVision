from __future__ import annotations

"""Integration tests for Redis-backed cache.

These tests require a running Redis instance at the URL specified
in Django settings. They are marked with ``pytest.mark.django_db``
but use the external Redis service.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.common.domain.value_objects import Symbol
from apps.market_data.domain.entities import Candle, Quote
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.cache import CandleCache, QuoteCache
from core.redis_client import get_redis_client


@pytest.mark.django_db
class TestQuoteCacheIntegration:
    @pytest.fixture
    def cache(self) -> QuoteCache:
        return QuoteCache()

    @pytest.fixture
    def symbol(self) -> Symbol:
        return Symbol(exchange="NSE", tradingsymbol="RELIANCE")

    def test_set_and_get(self, cache: QuoteCache, symbol: Symbol) -> None:
        quote = Quote(
            symbol="NSE:RELIANCE",
            ltp=Decimal("2500.50"),
            volume=100000,
            tick_at=datetime(2025, 3, 10, 10, 0, tzinfo=timezone.utc),
        )
        cache.set(symbol, quote)

        cached = cache.get(symbol)
        assert cached is not None
        assert cached.ltp == quote.ltp
        assert cached.volume == quote.volume

    def test_get_missing(self, cache: QuoteCache, symbol: Symbol) -> None:
        result = cache.get(symbol)
        assert result is None

    def test_delete(self, cache: QuoteCache, symbol: Symbol) -> None:
        quote = Quote(
            symbol="NSE:RELIANCE",
            ltp=Decimal("100.00"),
            volume=5000,
            tick_at=datetime(2025, 3, 10, 10, 0, tzinfo=timezone.utc),
        )
        cache.set(symbol, quote)
        cache.delete(symbol)

        result = cache.get(symbol)
        assert result is None


@pytest.mark.django_db
class TestCandleCacheIntegration:
    @pytest.fixture
    def cache(self) -> CandleCache:
        return CandleCache()

    @pytest.fixture
    def symbol(self) -> Symbol:
        return Symbol(exchange="NSE", tradingsymbol="RELIANCE", instrument_token=1001)

    def test_set_and_get(self, cache: CandleCache, symbol: Symbol) -> None:
        candles = [
            Candle(
                instrument_token=1001,
                timeframe="15min",
                timestamp=datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=50000,
            ),
        ]
        cache.set(symbol, Timeframe.MINUTE_15, candles)

        cached = cache.get(symbol, Timeframe.MINUTE_15)
        assert cached is not None
        assert len(cached) == 1
        assert cached[0].close == Decimal("103")
