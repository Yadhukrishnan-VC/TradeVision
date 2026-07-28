from __future__ import annotations

import logging
from typing import Any

from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.intelligence.infrastructure.ta_completed_handler import handle_ta_completed
from apps.intelligence.infrastructure.trading_signal_bridge import handle_signal_created

logger = logging.getLogger(__name__)


def register_handlers(event_bus: Any = None) -> None:
    bus = event_bus or get_event_bus()
    bus.subscribe(
        "signals.SignalCreated",
        handle_signal_created,
        consumer_group="intelligence",
    )
    bus.subscribe(
        "technical_analysis.TechnicalAnalysisCompleted",
        handle_ta_completed,
        consumer_group="intelligence",
    )
    logger.debug("intelligence_handlers_registered")
