from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

from celery import shared_task
from django.utils import timezone

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.market_data.application.market_data_service import get_market_data_service
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.repositories import CandleRepository, InstrumentRepository
from core.market_calendar import MarketSession, get_market_calendar
from core.redis_client import get_redis_client
from core.resilience.circuit_breaker import CircuitBreakerFactory
from core.utils import get_ist_now, get_now

logger = logging.getLogger(__name__)


def _publish_candles_persisted(
    instrument_token: int,
    timeframe: Timeframe,
    persisted: int,
    provider_name: str,
) -> None:
    """Publish a ``marketdata.CandlesPersisted`` event after candle persistence.

    Additive; the event currently has no subscribers (Technical Analysis
    ingestion remains webhook-driven) and completes the publisher-side
    event contract alongside ``marketdata.SessionStatusChanged``.
    """
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


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
    queue="market_data",
)
def refresh_candles(
    self: Any,
    instrument_token: int,
    timeframe: str,
) -> None:
    """Flush in-memory 1-minute tick buckets to the ``Candle`` table.

    Called periodically by Celery Beat or triggered after a batch of
    ticks is received.

    Args:
        instrument_token: The instrument to refresh candles for.
        timeframe:        Target aggregation interval.
    """
    try:
        service = get_market_data_service()
        tf = Timeframe.from_string(timeframe)

        if tf == Timeframe.MINUTE_1:
            return

        repo = CandleRepository()
        instrument_repo = InstrumentRepository()
        instrument = instrument_repo.find_by_token(instrument_token)
        if instrument is None:
            logger.warning(
                "refresh_candles_unknown_instrument",
                extra={"instrument_token": instrument_token},
            )
            return

        from apps.market_data.application.candle_aggregation_service import (
            CandleAggregationService,
        )
        from core.market_data.base_provider import MarketDataRequest
        from core.market_data.provider_factory import MarketDataProviderFactory

        provider = MarketDataProviderFactory.get_provider()
        now = get_now()

        request = MarketDataRequest(
            symbol=instrument.tradingsymbol,
            interval="1min",
            from_timestamp=now - timedelta(hours=2),
            to_timestamp=now,
        )
        response = provider.fetch(request)

        aggregator = CandleAggregationService()
        candles = aggregator.aggregate(
            instrument_token=instrument_token,
            base_candles=list(response.bars),
            target_timeframe=tf,
        )

        count = repo.bulk_upsert(candles)
        logger.info(
            "refresh_candles_complete",
            extra={
                "instrument_token": instrument_token,
                "timeframe": timeframe,
                "candles_persisted": count,
            },
        )

        _publish_candles_persisted(
            instrument_token=instrument_token,
            timeframe=tf,
            persisted=count,
            provider_name=provider.provider_name,
        )
    except Exception as exc:
        logger.error(
            "refresh_candles_failed",
            extra={
                "instrument_token": instrument_token,
                "timeframe": timeframe,
                "error": str(exc),
            },
        )
        raise self.retry(exc=exc)


_last_session_status: str | None = None


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
    queue="market_data",
)
def detect_session_transitions(self: Any) -> None:
    """Poll ``core.market_calendar`` for session changes and publish events.

    Compares the current ``MarketSession`` against the previously
    published value and emits ``marketdata.SessionStatusChanged`` only
    on an actual transition.

    This task is triggered by Celery Beat every 30 seconds during
    market hours.
    """
    global _last_session_status

    try:
        calendar = get_market_calendar()
        current_session = calendar.get_session(get_ist_now())
        current_status = current_session.value

        if _last_session_status is not None and _last_session_status == current_status:
            return

        _last_session_status = current_status

        event_bus = get_event_bus()
        event = DomainEvent.create(
            event_type="marketdata.SessionStatusChanged",
            payload={"status": current_status},
            correlation_id=uuid.uuid5(
                uuid.NAMESPACE_DNS,
                "marketdata.SessionStatusChanged",
            ),
            version=1,
        )
        event_bus.publish(event)

        logger.info(
            "session_transition_detected",
            extra={
                "from_status": _last_session_status,
                "to_status": current_status,
            },
        )
    except Exception as exc:
        logger.error(
            "session_transition_detect_failed",
            extra={"error": str(exc)},
        )
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=0,
    acks_late=True,
    queue="market_data",
)
def reconnect_websocket_watchdog(self: Any) -> None:
    """Force-reconnect if the WebSocket tick manager is stuck in DEGRADED.

    This task is triggered by Celery Beat at a low frequency and is
    self-healing — it does not retry on failure.
    """
    try:
        redis_client = get_redis_client()
        state = redis_client.get("market_data:websocket:state")

        if state and state in (b"degraded", "degraded"):
            logger.warning("websocket_watchdog_detected_stuck_degraded")
            from apps.market_data.infrastructure.websocket_manager import (
                WebSocketTickManager,
            )

            # The manager will attempt reconnection via its own loop;
            # this watchdog ensures the loop is restarted if stuck.
            redis_client.set("market_data:websocket:state", "connecting")
            logger.info("websocket_watchdog_triggered_reconnect")
    except Exception as exc:
        logger.error(
            "websocket_watchdog_error",
            extra={"error": str(exc)},
        )


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    queue="market_data",
    time_limit=600,
)
def run_historical_sync(
    self: Any,
    instrument_token: int,
    timeframe: str,
    from_days_ago: int = 30,
) -> int:
    """On-demand backfill of historical candle data.

    Args:
        instrument_token: The instrument to backfill.
        timeframe:        Target aggregation interval.
        from_days_ago:    Number of days of history to fetch.

    Returns:
        Number of candles persisted.
    """
    try:
        from apps.market_data.application.historical_sync_service import (
            get_historical_sync_service,
        )

        service = get_historical_sync_service()
        tf = Timeframe.from_string(timeframe)
        now = get_now()
        from_ts = now - timedelta(days=from_days_ago)

        count = service.backfill(
            instrument_token=instrument_token,
            timeframe=tf,
            from_timestamp=from_ts,
            to_timestamp=now,
        )
        logger.info(
            "historical_sync_task_complete",
            extra={
                "instrument_token": instrument_token,
                "timeframe": timeframe,
                "candles_persisted": count,
            },
        )
        return count
    except Exception as exc:
        logger.error(
            "historical_sync_task_failed",
            extra={
                "instrument_token": instrument_token,
                "timeframe": timeframe,
                "error": str(exc),
            },
        )
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    queue="maintenance",
    time_limit=300,
)
def sync_instrument_master(self: Any) -> dict[str, int]:
    """Nightly instrument dump synchronisation.

    Called by Celery Beat once per day after market close.
    """
    try:
        from apps.market_data.application.instrument_sync_service import (
            get_instrument_sync_service,
        )

        service = get_instrument_sync_service()
        result = service.sync()
        logger.info(
            "instrument_master_sync_complete",
            extra=result,
        )
        return result
    except Exception as exc:
        logger.error(
            "instrument_master_sync_failed",
            extra={"error": str(exc)},
        )
        raise self.retry(exc=exc)
