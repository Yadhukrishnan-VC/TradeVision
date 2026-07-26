from __future__ import annotations

import logging
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

logger = logging.getLogger(__name__)

# Consumer groups for market_data event handlers
_MARKET_DATA_CONSUMER_GROUP = "market_data"


def register_handlers(event_bus: Any = None) -> None:
    """Register market_data event handlers on the event bus.

    Currently, ``market_data`` is primarily a *publisher* of events
    (``marketdata.SessionStatusChanged``, ``marketdata.PriceTick``).
    Handlers for events consumed by ``market_data`` will be registered
    here as they are added in future batches.

    Args:
        event_bus: Event bus instance. Defaults to the process-wide singleton.
    """
    bus = event_bus or get_event_bus()

    # Future subscriptions (Batch 3+):
    # bus.subscribe("orders.OrderFilled", handle_order_filled, ...)
    # bus.subscribe("positions.PositionOpened", handle_position_opened, ...)
    logger.debug("market_data_event_handlers_registered")


def handle_session_status_changed(event: DomainEvent) -> None:
    """Handle ``marketdata.SessionStatusChanged`` events.

    This handler is registered by the dashboard's trading_core consumer
    group. This function exists here for completeness and potential
    future internal consumption.
    """
    logger.info(
        "session_status_changed",
        extra={
            "new_status": event.payload.get("status"),
            "event_id": str(event.event_id),
        },
    )


def handle_price_tick(event: DomainEvent) -> None:
    """Handle ``marketdata.PriceTick`` events internally.

    This is a no-op stub for now. It will be used by the ``portfolio``
    app's position-monitoring service in Batch 3.
    """
    logger.debug(
        "price_tick_received",
        extra={
            "symbol": event.payload.get("symbol"),
            "ltp": event.payload.get("ltp"),
            "event_id": str(event.event_id),
        },
    )
