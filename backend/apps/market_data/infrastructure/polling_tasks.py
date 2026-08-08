"""
Batch M4 — Real Market Data REST polling bridge (Celery tasks).

One Beat-driven task (``poll_market_data_watchlist``) polls the configured
``MARKET_DATA_POLL_WATCHLIST`` during market hours on
``MARKET_DATA_POLL_INTERVAL_SECONDS``. For each watchlist symbol it:

    1. backfills the trailing window of ``MARKET_DATA_POLL_TIMEFRAME`` candles
       via the existing ``HistoricalSyncService`` (idempotent upsert, provider
       circuit breaker, ``marketdata.CandlesPersisted``),
    2. resolves the newest persisted candle and feeds it through the
       ``CandleToTechnicalAnalysisBridge`` into the existing TA ingestion seam.

Semantics (per the batch contract):

    * No-ops outside market hours and when the watchlist is empty.
    * Per-symbol isolation: one symbol's failure is logged and skipped; the
      rest of the watchlist still processes.
    * Stale / duplicate / empty-bar outcomes are logged-and-skipped, never
      raised. Only genuinely transient failures (provider outage surfaced as
      ``DataProviderError``) re-queue the whole watchlist for retry, matching
      the loop-protection pattern of the other ``market_data`` tasks.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.conf import settings

from apps.common.domain.value_objects import Symbol
from apps.market_data.application.candle_ta_bridge import get_candle_ta_bridge
from apps.market_data.application.historical_sync_service import get_historical_sync_service
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.repositories import CandleRepository, InstrumentRepository
from core.exceptions import DataProviderError
from core.market_calendar import MarketSession, get_market_calendar
from core.utils import get_ist_now, get_now, to_utc

logger = logging.getLogger(__name__)


def _parse_watchlist(raw: str) -> list[tuple[str, str]]:
    """Parse ``EXCHANGE:SYMBOL`` pairs from a comma-separated config string.

    Mirrors the settings-parser contract so the task stays usable in tests
    regardless of how the operator supplied the watchlist.
    """
    result: list[tuple[str, str]] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        exchange, sep, symbol = token.partition(":")
        if not sep or not exchange.strip() or not symbol.strip():
            raise ValueError(
                f"Invalid watchlist entry {token!r}. Expected 'EXCHANGE:SYMBOL'."
            )
        result.append((exchange.strip().upper(), symbol.strip().upper()))
    return result


def poll_watchlist_sync(watchlist: list[tuple[str, str]]) -> int:
    """Synchronously poll one watchlist cycle.

    Exposed separately from the Celery task so integration tests can drive a
    full cycle deterministically (and reuse the exact production code path).

    Args:
        watchlist: List of ``(exchange, tradingsymbol)`` pairs.

    Returns:
        Number of candles published through the TA ingestion seam.

    Raises:
        DataProviderError: If a provider-wide outage is detected across the
            watchlist (the Celery task wraps this in ``self.retry``).
    """
    if not watchlist:
        logger.info("market_data_poll_empty_watchlist")
        return 0

    timeframe_raw = str(getattr(settings, "MARKET_DATA_POLL_TIMEFRAME", "1min"))
    try:
        timeframe = Timeframe.from_string(timeframe_raw)
    except ValueError:
        logger.error(
            "market_data_poll_invalid_timeframe",
            extra={"timeframe": timeframe_raw},
        )
        return 0

    calendar = get_market_calendar()
    session = calendar.get_session(get_ist_now())
    if session not in (MarketSession.MARKET_HOURS, MarketSession.PRE_MARKET):
        logger.info(
            "market_data_poll_outside_market_hours",
            extra={"session": session.value},
        )
        return 0

    now = to_utc(get_now())
    window_seconds = int(getattr(settings, "MARKET_DATA_POLL_WINDOW_SECONDS", 600))
    from_timestamp = now - timedelta(seconds=window_seconds)

    service = get_historical_sync_service()
    bridge = get_candle_ta_bridge()
    instrument_repo = InstrumentRepository()
    candle_repo = CandleRepository()

    published = 0
    provider_outage = False

    for exchange, symbol in watchlist:
        try:
            instrument = instrument_repo.find_by_symbol(
                Symbol(exchange=exchange, tradingsymbol=symbol)
            )
            if instrument is None:
                logger.warning(
                    "market_data_poll_unknown_symbol",
                    extra={"exchange": exchange, "symbol": symbol},
                )
                continue

            persisted = service.backfill(
                instrument_token=instrument.instrument_token,
                timeframe=timeframe,
                from_timestamp=from_timestamp,
                to_timestamp=now,
            )
            if persisted <= 0:
                logger.info(
                    "market_data_poll_no_new_candles",
                    extra={"exchange": exchange, "symbol": symbol},
                )
                continue

            latest = candle_repo.find_latest(instrument.instrument_token, timeframe.value, limit=1)
            if not latest:
                logger.info(
                    "market_data_poll_latest_missing",
                    extra={"exchange": exchange, "symbol": symbol},
                )
                continue

            candle = bridge.ingest_fresh_candle(
                instrument.instrument_token,
                timeframe.value,
                latest[-1].timestamp,
            )
            if candle is not None:
                published += 1
        except DataProviderError as exc:
            provider_outage = True
            logger.error(
                "market_data_poll_symbol_provider_error",
                extra={"exchange": exchange, "symbol": symbol, "error": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001 — per-symbol isolation contract
            logger.error(
                "market_data_poll_symbol_failed",
                extra={"exchange": exchange, "symbol": symbol, "error": str(exc)},
            )

    if provider_outage:
        raise DataProviderError(
            "market_data poll provider outage for at least one watchlist symbol"
        )

    logger.info(
        "market_data_poll_complete",
        extra={
            "watchlist_size": len(watchlist),
            "candles_published": published,
        },
    )
    return published


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
    queue="market_data",
)
def poll_market_data_watchlist(self: Any) -> int:
    """Celery Beat entry point for the REST polling bridge.

    ``CELERY_BEAT_SCHEDULE`` fires this every ``MARKET_DATA_POLL_INTERVAL_SECONDS``
    on the ``market_data`` queue. The task delegates to
    :func:`poll_watchlist_sync` and re-raises transient provider outages as a
    Celery retry; per-symbol failures are already isolated inside the cycle.
    """
    try:
        watchlist = list(getattr(settings, "MARKET_DATA_POLL_WATCHLIST", []) or [])
        return poll_watchlist_sync(watchlist)
    except DataProviderError as exc:
        logger.error("market_data_poll_retry", extra={"error": str(exc)})
        raise self.retry(exc=exc)
    except Exception as exc:
        logger.error("market_data_poll_failed", extra={"error": str(exc)})
        raise self.retry(exc=exc)