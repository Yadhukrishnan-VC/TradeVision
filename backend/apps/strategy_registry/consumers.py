from __future__ import annotations

import logging

from apps.eventbus.application.services import EventBusService
from core.events.event_types import EventType

logger = logging.getLogger(__name__)


def register_consumers() -> None:
    bus = EventBusService()
    bus.subscribe(
        event_type=EventType.PRICE_MOVEMENT,
        handler="apps.strategy_registry.tasks.match_packet",
    )
    logger.info("strategy_registry_consumers_registered")
