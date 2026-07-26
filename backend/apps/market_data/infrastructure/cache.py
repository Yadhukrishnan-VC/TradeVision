from __future__ import annotations

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.common.domain.value_objects import Symbol
from apps.market_data.domain.entities import Candle, Quote
from apps.market_data.domain.value_objects import Timeframe
from core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_QUOTE_TTL_SECONDS: int = 5
_STALE_QUOTE_TTL_SECONDS: int = 300


class QuoteCache:
    """Redis-backed cache for latest quotes with 5-second TTL.

    Keys: ``quote:{exchange}:{tradingsymbol}``
    """

    def __init__(self) -> None:
        self._redis = get_redis_client()

    @staticmethod
    def _key(symbol: Symbol) -> str:
        return f"quote:{symbol.exchange}:{symbol.tradingsymbol}"

    def get(self, symbol: Symbol) -> Quote | None:
        """Return a fresh quote from cache, or ``None`` if absent/expired."""
        data = self._redis.get(self._key(symbol))
        if data is None:
            return None
        return self._deserialize(data)

    def get_stale(self, symbol: Symbol) -> Quote | None:
        """Return any cached quote (even past TTL) or ``None``.

        Used for graceful degradation when the provider is unavailable.
        """
        key = self._key(symbol)
        ttl = self._redis.ttl(key)
        if ttl < 0 and ttl != -2:
            return None
        data = self._redis.get(key)
        if data is None:
            return None
        return self._deserialize(data)

    def set(self, symbol: Symbol, quote: Quote) -> None:
        """Store a quote with the standard TTL."""
        data = self._serialize(quote)
        self._redis.setex(self._key(symbol), _QUOTE_TTL_SECONDS, data)

    def set_stale(self, symbol: Symbol, quote: Quote) -> None:
        """Store a quote with an extended stale TTL for fallback reads."""
        data = self._serialize(quote)
        self._redis.setex(self._key(symbol), _STALE_QUOTE_TTL_SECONDS, data)

    def delete(self, symbol: Symbol) -> None:
        """Remove a quote from cache."""
        self._redis.delete(self._key(symbol))

    @staticmethod
    def _serialize(quote: Quote) -> str:
        return json.dumps({
            "symbol": quote.symbol,
            "ltp": str(quote.ltp),
            "volume": quote.volume,
            "tick_at": quote.tick_at.isoformat() if quote.tick_at else "",
            "bid": str(quote.bid) if quote.bid is not None else None,
            "ask": str(quote.ask) if quote.ask is not None else None,
        })

    @staticmethod
    def _deserialize(data: str) -> Quote:
        obj = json.loads(data)
        return Quote(
            symbol=obj["symbol"],
            ltp=Decimal(obj["ltp"]),
            volume=obj["volume"],
            tick_at=datetime.fromisoformat(obj["tick_at"]) if obj.get("tick_at") else datetime.min,
            bid=Decimal(obj["bid"]) if obj.get("bid") else None,
            ask=Decimal(obj["ask"]) if obj.get("ask") else None,
        )


class CandleCache:
    """Redis-backed cache for candle lists with per-timeframe TTL.

    Keys: ``candles:{instrument_token}:{timeframe}:latest``
    """

    def __init__(self) -> None:
        self._redis = get_redis_client()

    @staticmethod
    def _key(instrument_token: int, timeframe: str) -> str:
        return f"candles:{instrument_token}:{timeframe}:latest"

    def get(self, symbol: Symbol, timeframe: Timeframe) -> list[Candle] | None:
        """Return cached candles, or ``None`` if absent."""
        instrument_token = symbol.instrument_token
        if instrument_token is None:
            return None
        data = self._redis.get(self._key(instrument_token, timeframe.value))
        if data is None:
            return None
        return self._deserialize_list(data)

    def set(self, symbol: Symbol, timeframe: Timeframe, candles: list[Candle]) -> None:
        """Cache a list of candles with the per-timeframe TTL."""
        instrument_token = symbol.instrument_token
        if instrument_token is None:
            return
        data = self._serialize_list(candles)
        ttl = timeframe.cache_ttl_seconds
        self._redis.setex(self._key(instrument_token, timeframe.value), ttl, data)

    def delete(self, symbol: Symbol, timeframe: Timeframe) -> None:
        """Remove cached candles for the given instrument and timeframe."""
        instrument_token = symbol.instrument_token
        if instrument_token is None:
            return
        self._redis.delete(self._key(instrument_token, timeframe.value))

    @staticmethod
    def _serialize_list(candles: list[Candle]) -> str:
        return json.dumps([
            {
                "instrument_token": c.instrument_token,
                "timeframe": c.timeframe,
                "timestamp": c.timestamp.isoformat(),
                "open": str(c.open),
                "high": str(c.high),
                "low": str(c.low),
                "close": str(c.close),
                "volume": c.volume,
            }
            for c in candles
        ])

    @staticmethod
    def _deserialize_list(data: str) -> list[Candle]:
        objs = json.loads(data)
        return [
            Candle(
                instrument_token=o["instrument_token"],
                timeframe=o["timeframe"],
                timestamp=datetime.fromisoformat(o["timestamp"]),
                open=Decimal(o["open"]),
                high=Decimal(o["high"]),
                low=Decimal(o["low"]),
                close=Decimal(o["close"]),
                volume=o["volume"],
            )
            for o in objs
        ]
