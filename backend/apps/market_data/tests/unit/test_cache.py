from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.common.domain.value_objects import Symbol
from apps.market_data.domain.entities import Candle, Quote
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.cache import CandleCache, QuoteCache


class TestQuoteCacheSerialization:
    def test_serialize_deserialize_roundtrip(self) -> None:
        symbol = Symbol(exchange="NSE", tradingsymbol="RELIANCE")

        quote = Quote(
            symbol="NSE:RELIANCE",
            ltp=Decimal("2500.50"),
            volume=100000,
            tick_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=timezone.utc),
            bid=Decimal("2499.00"),
            ask=Decimal("2501.00"),
        )

        serialized = QuoteCache._serialize(quote)
        deserialized = QuoteCache._deserialize(serialized)

        assert deserialized.symbol == quote.symbol
        assert deserialized.ltp == quote.ltp
        assert deserialized.volume == quote.volume
        assert deserialized.tick_at == quote.tick_at
        assert deserialized.bid == quote.bid
        assert deserialized.ask == quote.ask

    def test_serialize_with_none_bid_ask(self) -> None:
        quote = Quote(
            symbol="NSE:TCS",
            ltp=Decimal("3500.00"),
            volume=50000,
            tick_at=datetime(2025, 3, 10, 10, 0, 0, tzinfo=timezone.utc),
        )
        serialized = QuoteCache._serialize(quote)
        deserialized = QuoteCache._deserialize(serialized)
        assert deserialized.bid is None
        assert deserialized.ask is None

    def test_cache_key_format(self) -> None:
        symbol = Symbol(exchange="NSE", tradingsymbol="RELIANCE")
        key = QuoteCache._key(symbol)
        assert key == "quote:NSE:RELIANCE"


class TestCandleCacheSerialization:
    def test_serialize_deserialize_roundtrip(self) -> None:
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
            Candle(
                instrument_token=1001,
                timeframe="15min",
                timestamp=datetime(2025, 3, 10, 9, 30, tzinfo=timezone.utc),
                open=Decimal("103"),
                high=Decimal("108"),
                low=Decimal("102"),
                close=Decimal("107"),
                volume=60000,
            ),
        ]

        serialized = CandleCache._serialize_list(candles)
        deserialized = CandleCache._deserialize_list(serialized)

        assert len(deserialized) == 2
        for orig, desc in zip(candles, deserialized):
            assert orig.instrument_token == desc.instrument_token
            assert orig.timeframe == desc.timeframe
            assert orig.open == desc.open
            assert orig.high == desc.high
            assert orig.low == desc.low
            assert orig.close == desc.close
            assert orig.volume == desc.volume

    def test_cache_key_format(self) -> None:
        key = CandleCache._key(1001, "15min")
        assert key == "candles:1001:15min:latest"
