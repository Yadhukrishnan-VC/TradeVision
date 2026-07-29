from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.intelligence.models import PineOutput
from apps.technical_analysis.application.services import CANONICAL_FIELD_MAP
from apps.technical_analysis.infrastructure.repositories import TASnapshotRepository
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
        ts = payload.get("snapshot_timestamp", event.occurred_at.isoformat())
        indicators = payload.get("indicators", {})

        sys_packet = DomainEvent.create(
            event_type="intelligence.PacketEnriched",
            payload={
                "symbol": symbol,
                "snapshot_id": payload.get("snapshot_id", ""),
                "exchange": payload.get("exchange", ""),
                "timeframe": payload.get("timeframe", ""),
                "snapshot_timestamp": ts,
                "indicators": indicators,
                "price": payload.get("price", {}),
                "pine_id": payload.get("pine_id", ""),
                "pine_version": payload.get("pine_version", ""),
                "packet_data": _serialize_packet(packet),
            },
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
        )
        bus.publish(sys_packet)

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
    raw_indicators: dict[str, Any] = payload.get("indicators", {})
    raw_price: dict[str, Any] = payload.get("price", {})
    try:
        ts_str = payload.get("snapshot_timestamp", "")
        if ts_str:
            detected_ts = datetime.fromisoformat(ts_str)
        else:
            detected_ts = datetime.now(timezone.utc)
    except (ValueError, TypeError):
        detected_ts = datetime.now(timezone.utc)

    indicators: dict[str, Any] = dict(raw_indicators)
    indicators["current_price"] = raw_price.get("close", "0")

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


def _to_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return None


def _get_prev_close(symbol: str, price_data: dict[str, Any]) -> Decimal | None:
    prev_close_raw = price_data.get("prev_close")
    if prev_close_raw is not None:
        try:
            return Decimal(str(prev_close_raw))
        except (ValueError, TypeError, ArithmeticError):
            return None

    try:
        repo = TASnapshotRepository()
        snapshots = repo.find_by_symbol(symbol, limit=2)
        if len(snapshots) >= 2:
            prev = snapshots[1]
            for raw_key, raw_value in prev.raw_payload.items():
                canonical = CANONICAL_FIELD_MAP.get(str(raw_key).lower().strip(), str(raw_key).lower().strip())
                if canonical == "close":
                    return Decimal(str(raw_value))
    except Exception:
        pass
    return None


def _build_packet(payload: dict[str, Any], occurred_at: datetime) -> IntelligencePacket:
    symbol = payload.get("symbol", "UNKNOWN")
    indicators: dict[str, Any] = payload.get("indicators", {})
    price_data: dict[str, Any] = payload.get("price", {})

    current_price = _to_decimal(price_data.get("close")) or Decimal("0")
    open_price = _to_decimal(price_data.get("open")) or Decimal("0")
    high = _to_decimal(price_data.get("high")) or Decimal("0")
    low = _to_decimal(price_data.get("low")) or Decimal("0")

    change_pct_raw = price_data.get("change_pct")
    if change_pct_raw is not None:
        change_pct = _optional_decimal(change_pct_raw)
        prev_close = _get_prev_close(symbol, price_data)
    else:
        prev_close = _get_prev_close(symbol, price_data)
        if prev_close is not None and prev_close != Decimal("0"):
            change_pct = ((current_price - prev_close) / prev_close) * Decimal("100")
        else:
            change_pct = None

    price_ctx = PriceContext(
        current_price=current_price,
        open_price=open_price,
        high=high,
        low=low,
        prev_close=prev_close,
        change_pct=change_pct,
        volume=int(price_data.get("volume", 0)),
        avg_volume_20d=0,
        circuit_status=CircuitStatus.NORMAL,
    )

    tech_ctx = TechnicalContext(
        rsi_14=_optional_decimal(indicators.get("rsi_14")),
        macd=_optional_decimal(indicators.get("macd")),
        macd_signal=_optional_decimal(indicators.get("macd_signal")),
        bb_upper=_optional_decimal(indicators.get("bb_upper")),
        bb_lower=_optional_decimal(indicators.get("bb_lower")),
        ema_20=_optional_decimal(indicators.get("ema_20")),
        ema_50=_optional_decimal(indicators.get("ema_50")),
        ema_200=_optional_decimal(indicators.get("ema_200")),
        vwap=_optional_decimal(indicators.get("vwap")),
    )

    breadth_ctx = BreadthContext(
        sector_index_change_pct=_to_decimal(indicators.get("sector_index_change_pct")) or Decimal("0"),
        sector_advance_decline=_to_decimal(indicators.get("sector_advance_decline")) or Decimal("0"),
        nifty_change_pct=_to_decimal(indicators.get("nifty_change_pct")) or Decimal("0"),
        sensex_change_pct=_to_decimal(indicators.get("sensex_change_pct")) or Decimal("0"),
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
