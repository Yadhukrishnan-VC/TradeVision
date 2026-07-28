from __future__ import annotations

import logging
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.signals_engine.infrastructure.tasks import handle_raw_alert_received

logger = logging.getLogger(__name__)


def register_handlers(event_bus: Any = None) -> None:
    bus = event_bus or get_event_bus()
    bus.subscribe(
        "ingestion.RawAlertReceived",
        handle_raw_alert_received,
        consumer_group="signals_engine",
    )
    logger.debug("signals_engine_handlers_registered")
