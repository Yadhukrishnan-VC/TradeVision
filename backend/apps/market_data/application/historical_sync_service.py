from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from apps.market_data.domain.entities import Candle
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.repositories import CandleRepository, InstrumentRepository
from core.exceptions import DataProviderError
from core.market_data.base_provider import MarketDataRequest, OHLCVBar
from core.market_data.provider_factory import MarketDataProviderFactory
from core.resilience.circuit_breaker import CircuitBreakerFactory, CircuitBreakerOpenError
from core.redis_client import get_redis_client
from core.utils import get_now, to_utc

logger = logging.getLogger(__name__)


class HistoricalSyncService:
    """Backfill missing candle history on demand.

    Uses the active provider's ``fetch()`` method (the same contract V1
    already uses) to retrieve historical OHLCV bars, then persists them
    as ``Candle`` rows.

    Construct via ``get_historical_sync_service()`` rather than directly.
    """

    def __init__(
        self,
        instrument_repo: InstrumentRepository | None = None,
        candle_repo: CandleRepository | None = None,
    ) -> None:
        self._instrument_repo = instrument_repo or InstrumentRepository()
        self._candle_repo = candle_repo or CandleRepository()
        redis_client = get_redis_client()
        self._circuit_factory = CircuitBreakerFactory(redis_client)

    def backfill(
        self,
        instrument_token: int,
        timeframe: Timeframe,
        from_timestamp: datetime,
        to_timestamp: datetime | None = None,
    ) -> int:
        """Backfill candle data for the given instrument and time range.

        Args:
            instrument_token: The instrument to backfill.
            timeframe:        Aggregation interval.
            from_timestamp:   Start of the range (UTC, timezone-aware).
            to_timestamp:     End of the range (UTC, timezone-aware).
                              Defaults to now.

        Returns:
            Number of candles persisted.

        Raises:
            DataProviderError: If the provider fetch fails.
        """
        end = to_timestamp or get_now()

        instrument = self._instrument_repo.find_by_token(instrument_token)
        if instrument is None:
            logger.warning(
                "historical_sync_unknown_instrument",
                extra={"instrument_token": instrument_token},
            )
            return 0

        tradingsymbol = instrument.tradingsymbol
        provider = MarketDataProviderFactory.get_provider()
        breaker = self._circuit_factory.get_or_create("historical-sync")

        request = MarketDataRequest(
            symbol=tradingsymbol,
            interval=timeframe.value,
            from_timestamp=to_utc(from_timestamp),
            to_timestamp=to_utc(end),
        )

        try:
            response = breaker.call(provider.fetch, request)
        except (DataProviderError, CircuitBreakerOpenError) as exc:
            logger.error(
                "historical_sync_fetch_failed",
                extra={
                    "instrument_token": instrument_token,
                    "timeframe": timeframe.value,
                    "error": str(exc),
                },
            )
            raise DataProviderError(
                f"Historical sync failed for {tradingsymbol}: {exc}"
            ) from exc

        persisted = self._persist_candles(instrument_token, timeframe, response.bars)

        self._publish_candles_persisted(
            instrument_token=instrument_token,
            timeframe=timeframe,
            persisted=persisted,
            provider_name=provider.provider_name,
        )

        logger.info(
            "historical_sync_complete",
            extra={
                "instrument_token": instrument_token,
                "timeframe": timeframe.value,
                "bars_fetched": len(response.bars),
                "candles_persisted": persisted,
            },
        )
        return persisted

    def _persist_candles(
        self,
        instrument_token: int,
        timeframe: Timeframe,
        bars: tuple[OHLCVBar, ...],
    ) -> int:
        """Convert ``OHLCVBar`` tuples to ``Candle`` rows and upsert them."""
        count = 0
        for bar in bars:
            self._candle_repo.upsert(
                instrument_token=instrument_token,
                timeframe=timeframe.value,
                timestamp=to_utc(bar.timestamp),
                open=bar.open_price,
                high=bar.high,
                low=bar.low,
                close=bar.close_price,
                volume=bar.volume,
            )
            count += 1
        return count

    def _publish_candles_persisted(
        self,
        instrument_token: int,
        timeframe: Timeframe,
        persisted: int,
        provider_name: str,
    ) -> None:
        """Publish a ``marketdata.CandlesPersisted`` event after a successful backfill.

        The event is additive and currently has no subscribers; it completes
        the publisher-side event contract alongside ``marketdata.SessionStatusChanged``
        and unblocks a future, separately-scoped Technical Analysis consumption path.
        """
        import uuid

        from apps.eventbus.domain.events import DomainEvent
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        event = DomainEvent.create(
            event_type="marketdata.CandlesPersisted",
            payload={
                "instrument_token": instrument_token,
                "timeframe": timeframe.value,
                "candle_count": persisted,
                "provider": provider_name,
            },
            correlation_id=uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"marketdata.CandlesPersisted:{instrument_token}:{timeframe.value}",
            ),
            version=1,
        )
        get_event_bus().publish(event)


_service_instance: HistoricalSyncService | None = None


def get_historical_sync_service() -> HistoricalSyncService:
    """Return a process-wide ``HistoricalSyncService`` singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = HistoricalSyncService()
    return _service_instance


def reset_historical_sync_service() -> None:
    """Reset the singleton (primarily for testing)."""
    global _service_instance
    _service_instance = None
