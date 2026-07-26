from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.common.domain.value_objects import Symbol


@dataclass(frozen=True)
class Instrument:
    """Domain entity representing a tradeable financial instrument.

    This is the DB-free domain view of an instrument. Persistence is
    handled by the ORM model in ``infrastructure.models``.

    Attributes:
        instrument_token: Exchange-assigned numeric token (primary key).
        exchange:         Exchange code (e.g. ``"NSE"``, ``"BSE"``).
        tradingsymbol:    Exchange-listed trading symbol (e.g. ``"RELIANCE"``).
        name:             Human-readable company name.
        segment:          Market segment (e.g. ``"EQUITY"``, ``"FNO"``).
        lot_size:         Minimum trade quantity.
        tick_size:        Minimum price increment.
        instrument_type:  Instrument category (e.g. ``"EQ"``, ``"FUT"``, ``"OPT"``).
        expiry:           For derivatives, the contract expiry date.
        is_active:        Whether this instrument is currently tradeable.
    """

    instrument_token: int
    exchange: str
    tradingsymbol: str
    name: str
    segment: str
    lot_size: int
    tick_size: Decimal
    instrument_type: str
    expiry: datetime | None = None
    is_active: bool = True

    def to_symbol(self) -> Symbol:
        """Return a ``Symbol`` value object for this instrument."""
        return Symbol(
            exchange=self.exchange,
            tradingsymbol=self.tradingsymbol,
            instrument_token=self.instrument_token,
            segment=self.segment,
        )


@dataclass(frozen=True)
class Candle:
    """Domain entity representing an aggregated OHLCV candle.

    Attributes:
        instrument_token: Identifies the instrument this candle belongs to.
        timeframe:        Aggregation interval (e.g. ``"15min"``).
        timestamp:        Candle open time (UTC, timezone-aware).
        open:             Opening price.
        high:             Highest price during the interval.
        low:              Lowest price during the interval.
        close:            Closing price.
        volume:           Total traded volume.
    """

    instrument_token: int
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class Quote:
    """Real-time last-trade price and volume for an instrument.

    A ``Quote`` is always the latest known market state for a given
    instrument. It is never stored permanently; it exists in the
    ``QuoteCache`` (Redis) with a 5-second TTL.

    Attributes:
        symbol:      The fully qualified instrument identifier.
        ltp:         Last traded price.
        volume:      Cumulative traded volume for the trading day.
        tick_at:     UTC datetime of the trade that produced this quote.
        bid:         Current best bid price (optional, may not be available).
        ask:         Current best ask price (optional, may not be available).
    """

    symbol: str
    ltp: Decimal
    volume: int
    tick_at: datetime
    bid: Decimal | None = None
    ask: Decimal | None = None
