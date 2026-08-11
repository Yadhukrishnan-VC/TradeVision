"""PIPELINE-HEALTH-1 — heartbeat recording service.

Maps inbound domain events to (stage, symbol_scope) and upserts the
corresponding ``StageHeartbeat``. Uses ``event.occurred_at`` as the
authoritative timestamp (never wall-clock), so replay, redelivery and
out-of-order processing stay correct by construction.
"""

from __future__ import annotations

import logging
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.pipeline_health.application.ports import StageHeartbeatRepository
from apps.pipeline_health.domain.entities import StageHeartbeat
from apps.pipeline_health.domain.exceptions import (
    MissingSymbolError,
    UnsupportedEventTypeError,
)
from apps.pipeline_health.domain.value_objects import Stage

logger = logging.getLogger(__name__)

# Event type -> (stage, symbol_scope extractor).
#
# symbol_scope is "GLOBAL" for non-per-symbol stages (execution) or the
# event's symbol for per-symbol stages. Market data carries only an
# ``instrument_token``; the symbol is resolved through the instrument
# repository (best-effort, see ``_market_data_scope``).
_MARKET_DATA = Stage.MARKET_DATA.value
_TECHNICAL_ANALYSIS = Stage.TECHNICAL_ANALYSIS.value
_INTELLIGENCE = Stage.INTELLIGENCE.value
_RULE_ENGINE = Stage.RULE_ENGINE.value
_EXECUTION = Stage.EXECUTION.value


class HeartbeatRecordingService:
    """Record stage heartbeats from upstream domain events."""

    def __init__(
        self,
        repository: StageHeartbeatRepository,
        symbol_resolver: Any = None,
    ) -> None:
        self._repository = repository
        self._symbol_resolver = symbol_resolver

    def record(self, event: DomainEvent) -> None:
        """Map the event and upsert its heartbeat (idempotent).

        Args:
            event: The consumed domain event.

        Raises:
            UnsupportedEventTypeError: For event types this service is not
                wired to map (defensive; consumers subscribe only to known
                types).
        """
        stage, symbol_scope = self._map_event(event)
        self._repository.upsert(
            stage=stage,
            symbol_scope=symbol_scope,
            last_event_at=event.occurred_at,
            last_event_id=event.event_id,
            last_correlation_id=event.correlation_id,
        )
        logger.debug(
            "pipeline_health_heartbeat_recorded",
            extra={
                "stage": stage.value,
                "symbol_scope": symbol_scope,
                "event_id": str(event.event_id),
            },
        )

    def _map_event(self, event: DomainEvent) -> tuple[Stage, str]:
        """Return the (stage, symbol_scope) for an event."""
        event_type = event.event_type
        payload = event.payload or {}

        if event_type == "marketdata.CandlesPersisted":
            return _MARKET_DATA_STAGE, self._market_data_scope(payload, event)
        if event_type == "technical_analysis.TechnicalAnalysisCompleted":
            return _TECHNICAL_ANALYSIS_STAGE, self._symbol_scope(payload, event)
        if event_type == "intelligence.PacketBuilt":
            return _INTELLIGENCE_STAGE, self._symbol_scope(payload, event)
        if event_type == "rule_engine.RuleFired":
            return _RULE_ENGINE_STAGE, self._symbol_scope(payload, event)
        if event_type == "orders.OrderFilled":
            return _EXECUTION_STAGE, "GLOBAL"
        raise UnsupportedEventTypeError(event_type)

    def _symbol_scope(self, payload: dict[str, Any], event: DomainEvent) -> str:
        """Return the event's symbol, raising when it cannot be resolved."""
        symbol = (payload.get("symbol") or "").strip().upper()
        if not symbol:
            raise MissingSymbolError(event.event_type, str(event.event_id))
        return symbol

    def _market_data_scope(self, payload: dict[str, Any], event: DomainEvent) -> str:
        """Resolve the CandlesPersisted instrument token to a symbol.

        Best-effort: when the instrument is unknown the scope falls back to
        a stable ``token:<instrument_token>`` key so the heartbeat is still
        recorded without corrupting the symbol dimension.
        """
        token = payload.get("instrument_token")
        if self._symbol_resolver is not None and token is not None:
            resolved = self._symbol_resolver(token)
            if resolved:
                return str(resolved).strip().upper()
        logger.warning(
            "pipeline_health_market_data_scope_unresolved",
            extra={
                "instrument_token": token,
                "event_id": str(event.event_id),
            },
        )
        return f"token:{token}"


_MARKET_DATA_STAGE = Stage.MARKET_DATA
_TECHNICAL_ANALYSIS_STAGE = Stage.TECHNICAL_ANALYSIS
_INTELLIGENCE_STAGE = Stage.INTELLIGENCE
_RULE_ENGINE_STAGE = Stage.RULE_ENGINE
_EXECUTION_STAGE = Stage.EXECUTION
