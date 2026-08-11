"""PIPELINE-HEALTH-1 — EventBus consumers.

Subscribes the heartbeat recording service to the upstream events that
evidence each pipeline stage's liveness.

NOTE on registration: per the batch package this module is named
``event_consumers.py`` (not ``infrastructure/event_handlers.py``), so
``EventBusService.register_all_handlers()`` auto-discovery does not pick it
up. It is wired explicitly from ``apps.py ready()`` via
``register_consumers(get_event_bus())``.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.market_data.infrastructure.repositories import InstrumentRepository
from apps.pipeline_health.application.heartbeat_recording_service import (
    HeartbeatRecordingService,
)
from apps.pipeline_health.domain.exceptions import (
    MissingSymbolError,
    UnsupportedEventTypeError,
)

logger = logging.getLogger(__name__)

_CONSUMER_GROUP = "pipeline_health"

# Event types evidencing each watched pipeline stage.
_MARKET_DATA_EVENT = "marketdata.CandlesPersisted"
_TECHNICAL_ANALYSIS_EVENT = "technical_analysis.TechnicalAnalysisCompleted"
_INTELLIGENCE_EVENT = "intelligence.PacketBuilt"
_RULE_ENGINE_EVENT = "rule_engine.RuleFired"
_EXECUTION_EVENT = "orders.OrderFilled"

_EVENT_TYPES = (
    _MARKET_DATA_EVENT,
    _TECHNICAL_ANALYSIS_EVENT,
    _INTELLIGENCE_EVENT,
    _RULE_ENGINE_EVENT,
    _EXECUTION_EVENT,
)


def _instrument_symbol_resolver(token: Any) -> str | None:
    """Resolve an instrument token to its tradingsymbol (best-effort)."""
    instrument = InstrumentRepository().find_by_token(int(token))
    if instrument is None:
        return None
    return getattr(instrument, "tradingsymbol", None)


_service: HeartbeatRecordingService | None = None


def _get_service() -> HeartbeatRecordingService:
    global _service
    if _service is None:
        from apps.pipeline_health.infrastructure.repositories import (
            StageHeartbeatRepository,
        )

        _service = HeartbeatRecordingService(
            repository=StageHeartbeatRepository(),
            symbol_resolver=_instrument_symbol_resolver,
        )
    return _service


def handle_pipeline_event(event: DomainEvent) -> None:
    """Record a heartbeat for any watched upstream event.

    Defensive boundary: a bad payload or unsupported event type is logged
    and swallowed so a malformed event can never take down the consuming
    handler or the pipeline.
    """
    try:
        _get_service().record(event)
    except (MissingSymbolError, UnsupportedEventTypeError) as exc:
        logger.warning(
            "pipeline_health_consumer_skipped",
            extra={
                "event_type": event.event_type,
                "event_id": str(event.event_id),
                "reason": str(exc),
            },
        )
    except Exception:
        logger.exception(
            "pipeline_health_consumer_failed",
            extra={
                "event_type": event.event_type,
                "event_id": str(event.event_id),
            },
        )


def register_consumers(event_bus: Any = None) -> None:
    """Subscribe the heartbeat recording handlers to the event bus.

    Args:
        event_bus: The EventBus to register on; defaults to the configured
            singleton (see ``get_event_bus``).
    """
    bus = event_bus or get_event_bus()
    for event_type in _EVENT_TYPES:
        bus.subscribe(
            event_type,
            handle_pipeline_event,
            consumer_group=_CONSUMER_GROUP,
        )
    logger.info(
        "pipeline_health_consumers_registered",
        extra={"consumer_group": _CONSUMER_GROUP},
    )
