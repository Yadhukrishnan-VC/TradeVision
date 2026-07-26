from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.common.domain.value_objects import Symbol
from apps.market_data.domain.entities import Candle, Instrument, Quote
from apps.market_data.domain.exceptions import (
    StaleCandleDataError,
    UnknownInstrumentError,
    UnsupportedTimeframeError,
)
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.cache import CandleCache, QuoteCache
from apps.market_data.infrastructure.repositories import CandleRepository, InstrumentRepository
from core.config import config
from core.exceptions import DataProviderError
from core.market_calendar import MarketCalendar, MarketSession, get_market_calendar
from core.market_data.base_provider import (
    BaseMarketDataProvider,
    MarketDataRequest,
    MarketDataResponse,
)
from core.market_data.provider_factory import MarketDataProviderFactory
from core.resilience.circuit_breaker import CircuitBreakerFactory, CircuitBreakerOpenError
from core.redis_client import get_redis_client
from core.utils import get_now, to_utc

logger = logging.getLogger(__name__)


class MarketDataService:
    """Public interface for market data queries used by other apps.

    ``MarketDataService`` is the single point of contact for any component
    (V1 ``technical_analysis`` or V2 ``portfolio``, ``risk_analysis``,
    ``decision_engine``, ``execution_engine``) that needs quotes, candles,
    or session state.

    It composes:
        - A ``MarketDataProvider`` (via the factory singleton) for live data.
        - ``InstrumentRepository`` / ``CandleRepository`` for persisted data.
        - ``QuoteCache`` / ``CandleCache`` for Redis-backed fast reads.
        - ``MarketCalendar`` for session-state queries (delegated entirely).
        - ``CircuitBreaker`` for provider-level resilience.

    Construct via ``get_market_data_service()`` rather than directly.
    """

    def __init__(
        self,
        instrument_repository: InstrumentRepository | None = None,
        candle_repository: CandleRepository | None = None,
        quote_cache: QuoteCache | None = None,
        candle_cache: CandleCache | None = None,
        calendar: MarketCalendar | None = None,
        circuit_breaker_factory: CircuitBreakerFactory | None = None,
    ) -> None:
        self._instrument_repo = instrument_repository or InstrumentRepository()
        self._candle_repo = candle_repository or CandleRepository()
        self._quote_cache = quote_cache or QuoteCache()
        self._candle_cache = candle_cache or CandleCache()
        self._calendar = calendar or get_market_calendar()
        redis_client = get_redis_client()
        self._circuit_factory = circuit_breaker_factory or CircuitBreakerFactory(redis_client)

    # ------------------------------------------------------------------
    # Quote
    # ------------------------------------------------------------------

    def get_quote(self, symbol: Symbol) -> Quote:
        """Return the latest known quote for *symbol*.

        Resolution order:
            1. ``QuoteCache`` (Redis, 5 s TTL) — fastest path.
            2. Provider fetch via ``BaseMarketDataProvider.fetch()``
               protected by ``CircuitBreaker``. On circuit open returns
               cached data with a staleness flag; never raises.
            3. If both cache and provider are unavailable, raises
               ``UnknownInstrumentError``.

        Args:
            symbol: The instrument to look up.

        Returns:
            The latest ``Quote`` for the requested symbol.

        Raises:
            UnknownInstrumentError: If the symbol is not in the
                ``Instrument`` table.
        """
        cached = self._quote_cache.get(symbol)
        if cached is not None:
            return cached

        instrument = self._instrument_repo.find_by_symbol(symbol)
        if instrument is None:
            raise UnknownInstrumentError(
                message=f"Instrument not found: {symbol.as_broker_string()}",
                details={"exchange": symbol.exchange, "tradingsymbol": symbol.tradingsymbol},
            )

        try:
            quote = self._fetch_latest_quote(instrument, symbol)
            self._quote_cache.set(symbol, quote)
            return quote
        except (DataProviderError, CircuitBreakerOpenError):
            logger.warning(
                "quote_fetch_failed_using_cached",
                extra={"symbol": symbol.as_broker_string()},
            )
            stale = self._quote_cache.get_stale(symbol)
            if stale is not None:
                return stale
            raise UnknownInstrumentError(
                message=f"Unable to fetch quote for {symbol.as_broker_string()}",
                code="PROVIDER_UNAVAILABLE",
            )

    def _fetch_latest_quote(self, instrument: Instrument, symbol: Symbol) -> Quote:
        provider = MarketDataProviderFactory.get_provider()
        now = get_now()
        request = MarketDataRequest(
            symbol=instrument.tradingsymbol,
            interval="1min",
            from_timestamp=to_utc(now.replace(hour=9, minute=15, second=0, microsecond=0)),
            to_timestamp=to_utc(now),
        )

        breaker = self._circuit_factory.get_or_create("quote-fetch")
        response: MarketDataResponse = breaker.call(provider.fetch, request)

        if not response.bars:
            raise DataProviderError(f"Empty response for {symbol.as_broker_string()}")

        latest_bar = response.bars[-1]
        return Quote(
            symbol=symbol.as_broker_string(),
            ltp=latest_bar.close_price,
            volume=latest_bar.volume,
            tick_at=latest_bar.timestamp,
        )

    # ------------------------------------------------------------------
    # Candles
    # ------------------------------------------------------------------

    def get_candles(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        lookback: int,
    ) -> list[Candle]:
        """Return aggregated OHLCV candles for *symbol*.

        Resolution order:
            1. ``CandleCache`` (Redis, per-timeframe TTL).
            2. Persisted ``Candle`` table via ``CandleRepository``.
            3. If persisted data is insufficient, raises
               ``StaleCandleDataError`` so the caller can invoke
               ``HistoricalSyncService``.

        Args:
            symbol:    The instrument to query.
            timeframe: Aggregation interval.
            lookback:  Number of candles to return (most recent first).

        Returns:
            Chronological list of ``Candle`` domain entities.

        Raises:
            UnknownInstrumentError: If *symbol* is not in the
                ``Instrument`` table.
            StaleCandleDataError: If not enough candle data is persisted.
            UnsupportedTimeframeError: If *timeframe* is not supported.
        """
        cached = self._candle_cache.get(symbol, timeframe)
        if cached is not None:
            return cached

        instrument = self._instrument_repo.find_by_symbol(symbol)
        if instrument is None:
            raise UnknownInstrumentError(
                message=f"Instrument not found: {symbol.as_broker_string()}",
                details={"exchange": symbol.exchange, "tradingsymbol": symbol.tradingsymbol},
            )

        candles = self._candle_repo.find_latest(
            instrument_token=instrument.instrument_token,
            timeframe=timeframe.value,
            limit=lookback,
        )

        if not candles or len(candles) < lookback:
            raise StaleCandleDataError(
                message=(
                    f"Insufficient candle data for {symbol.as_broker_string()} "
                    f"({timeframe.value}): have {len(candles)}, need {lookback}"
                ),
                details={
                    "requested": lookback,
                    "available": len(candles),
                    "timeframe": timeframe.value,
                },
            )

        self._candle_cache.set(symbol, timeframe, candles)
        return candles

    # ------------------------------------------------------------------
    # Market session (delegated to core.market_calendar)
    # ------------------------------------------------------------------

    def get_market_session(self) -> MarketSession:
        """Return the current NSE market session.

        Delegates entirely to ``core.market_calendar``. The returned
        ``MarketSession`` is one of ``pre_market``, ``market_hours``,
        ``post_market``, ``closed``, or ``holiday``.
        """
        from core.utils import get_ist_now

        return self._calendar.get_session(get_ist_now())

    def is_market_open(self, at: datetime | None = None) -> bool:
        """Return ``True`` if the market is currently in continuous trading.

        Args:
            at: Optional datetime to check (UTC, timezone-aware).
                Defaults to now in IST.
        """
        return self._calendar.is_market_hours(at)


_service_instance: MarketDataService | None = None


def get_market_data_service() -> MarketDataService:
    """Return a process-wide ``MarketDataService`` singleton.

    The provider reference is not cached here — it is resolved lazily
    inside each call via ``MarketDataProviderFactory.get_provider()``,
    which already implements its own singleton pattern.
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = MarketDataService()
    return _service_instance


def reset_market_data_service() -> None:
    """Reset the singleton (primarily for testing)."""
    global _service_instance
    _service_instance = None
