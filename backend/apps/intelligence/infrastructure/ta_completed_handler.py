from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.intelligence.models import PineOutput
from apps.intelligence.services import IntelligenceService
from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    DataQuality,
    IntelligencePacket,
    NewsContext,
    PriceContext,
    TechnicalContext,
)

logger = logging.getLogger(__name__)


def handle_ta_completed(event: DomainEvent) -> None:
    payload = event.payload
    symbol = payload.get("symbol", "")
    if not symbol:
        logger.warning("ta_completed_missing_symbol", extra={"event_id": str(event.event_id)})
        return

    _save_pine_outputs(payload)

    packet = _build_packet(payload, event.occurred_at)

    try:
        bus = get_event_bus()
        intel_service = IntelligenceService()

        ts = payload.get("snapshot_timestamp", event.occurred_at.isoformat())
        indicator_keys = payload.get("indicator_keys", [])

        sys_packet = DomainEvent.create(
            event_type="intelligence.PacketEnriched",
            payload={
                "symbol": symbol,
                "snapshot_id": payload.get("snapshot_id", ""),
                "exchange": payload.get("exchange", ""),
                "timeframe": payload.get("timeframe", ""),
                "snapshot_timestamp": ts,
                "indicator_keys": indicator_keys,
                "pine_id": payload.get("pine_id", ""),
                "pine_version": payload.get("pine_version", ""),
                "packet_data": _serialize_packet(packet),
            },
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
        )
        bus.publish(sys_packet)

        intel_service.build_packet(packet)

        logger.info(
            "ta_completed_processed",
            extra={
                "symbol": symbol,
                "snapshot_id": payload.get("snapshot_id"),
                "correlation_id": str(event.correlation_id),
            },
        )
    except Exception as exc:
        logger.exception(
            "ta_completed_processing_failed",
            extra={"symbol": symbol, "error": str(exc)},
        )


def _save_pine_outputs(payload: dict[str, Any]) -> None:
    symbol = payload.get("symbol", "")
    timeframe = payload.get("timeframe", "")
    indicator_keys = payload.get("indicator_keys", [])
    try:
        ts_str = payload.get("snapshot_timestamp", "")
        if ts_str:
            detected_ts = datetime.fromisoformat(ts_str)
        else:
            detected_ts = datetime.now(timezone.utc)
    except (ValueError, TypeError):
        detected_ts = datetime.now(timezone.utc)

    indicators: dict[str, Any] = {}
    for key in indicator_keys:
        indicators[key] = 0.0

    try:
        PineOutput.objects.update_or_create(
            symbol=symbol,
            timeframe=timeframe,
            indicator_name="pine_composite",
            defaults={
                "values": indicators,
                "detected_timestamp": detected_ts,
                "source": "pine_script",
            },
        )
    except Exception as exc:
        logger.warning(
            "pine_output_save_failed",
            extra={"symbol": symbol, "error": str(exc)},
        )


def _build_packet(payload: dict[str, Any], occurred_at: datetime) -> IntelligencePacket:
    symbol = payload.get("symbol", "UNKNOWN")
    indicator_keys = payload.get("indicator_keys", [])

    exchange = payload.get("exchange", "")
    timeframe = payload.get("timeframe", "")

    price_ctx = PriceContext(
        current_price=Decimal("0"),
        open_price=Decimal("0"),
        high=Decimal("0"),
        low=Decimal("0"),
        prev_close=Decimal("0"),
        change_pct=Decimal("0"),
        volume=0,
        avg_volume_20d=0,
        circuit_status=CircuitStatus.NORMAL,
    )

    tech_ctx = TechnicalContext()

    breadth_ctx = BreadthContext(
        sector_index_change_pct=Decimal("0"),
        sector_advance_decline=Decimal("0"),
        nifty_change_pct=Decimal("0"),
        sensex_change_pct=Decimal("0"),
    )

    dq = DataQuality(
        quality_score=0.95,
        missing_sources=(),
        stale_sources=(),
    )

    packet = IntelligencePacket(
        symbol=symbol,
        timestamp=occurred_at,
        freshness_validated=True,
        price_context=price_ctx,
        technical_context=tech_ctx,
        breadth_context=breadth_ctx,
        news_context=NewsContext(),
        data_quality=dq,
    )
    return packet


def _serialize_packet(packet: IntelligencePacket) -> dict[str, Any]:
    from dataclasses import asdict
    from core.events.event_bus import _EventEncoder
    import json
    return json.loads(json.dumps(asdict(packet), cls=_EventEncoder))
