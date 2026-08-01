from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.pattern_engine.infrastructure.tasks import run_pattern_analysis

logger = logging.getLogger(__name__)

SUBSCRIBED_EVENTS: dict[str, list[Any]] = {}


def handle_packet_built(event: DomainEvent) -> None:
    """Trigger a pattern analysis run when a fresh packet is built.

    The Pattern Engine subscribes to ``intelligence.PacketBuilt`` — the same
    stream the rule engine consumes — because that is the only event that
    carries the full ``IntelligencePacket``. ``rule_engine.RuleFired`` only
    carries the symbol/rule metadata, not the packet, so it cannot be used as
    the trigger for a packet-scoped analysis.

    Never raises: a failure here must not break the packet pipeline.
    """
    try:
        if not getattr(settings, "PATTERN_ENGINE_ENABLED", False):
            return

        payload = event.payload
        symbol = payload.get("symbol", "")
        if not symbol:
            logger.warning(
                "pe_packet_missing_symbol",
                extra={"event_id": str(event.event_id)},
            )
            return

        packet_data = payload.get("packet_data", payload)
        as_of = payload.get("snapshot_timestamp", "")

        run_pattern_analysis.delay(
            symbol=symbol,
            packet_data=packet_data,
            as_of=as_of,
            correlation_id=str(event.correlation_id),
            causation_id=str(event.event_id),
        )
        logger.info(
            "pe_packet_dispatched",
            extra={
                "symbol": symbol,
                "correlation_id": str(event.correlation_id),
                "causation_id": str(event.event_id),
            },
        )
    except Exception:
        logger.exception(
            "pe_packet_handler_failed",
            extra={"event_id": str(event.event_id)},
        )


SUBSCRIBED_EVENTS = {
    "intelligence.PacketBuilt": [handle_packet_built],
}


def register_handlers(event_bus: EventBus | None = None) -> None:
    """Register Pattern Engine event handlers (auto-discovered by EventBusService)."""
    bus = event_bus or get_event_bus()
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group="pattern_engine",
            )
    logger.debug("pattern_engine_handlers_registered")


__all__ = ["SUBSCRIBED_EVENTS", "register_handlers"]
