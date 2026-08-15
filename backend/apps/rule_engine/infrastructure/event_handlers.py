from __future__ import annotations

import json
import uuid
from collections.abc import Callable

from core.events.event_types import EnrichedIntelligencePacket
from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.rule_engine.infrastructure.tasks import evaluate_packet


def handle_enriched_packet(event: DomainEvent) -> None:
    data = event.payload
    enriched = _deserialize_enriched_packet(data.get("packet_data", data))
    # Idempotency key: the upstream intelligence.PacketBuilt payload does not
    # carry an `analysis_event_id` key, so a payload-derived value would always
    # be None and the (analysis_event_id, rule_id) UniqueConstraint could never
    # dedupe redelivered events. `event.event_id` is stable per stream entry /
    # redelivery, so it is used as the stable dedup key for all rules.
    analysis_event_id = event.event_id
    evaluate_packet.delay(
        enriched=_serialize_for_task(enriched),
        analysis_event_id=str(analysis_event_id),
    )


def _deserialize_enriched_packet(data: dict) -> EnrichedIntelligencePacket:
    from dataclasses import field
    from datetime import datetime
    from decimal import Decimal
    from typing import Any

    from core.events.event_types import (
        BreadthContext,
        CircuitStatus,
        DataQuality,
        IntelligencePacket,
        NewsContext,
        PriceContext,
        TechnicalContext,
    )

    packet_data = data.get("packet", data)
    price = packet_data.get("price_context", {})
    tech = packet_data.get("technical_context", {})
    breadth = packet_data.get("breadth_context", {})
    news = packet_data.get("news_context", {})
    dq = packet_data.get("data_quality", {})

    def to_decimal(v: Any) -> Decimal:
        return Decimal(str(v)) if v is not None else Decimal("0")

    def opt_decimal(v: Any) -> Decimal | None:
        return Decimal(str(v)) if v is not None else None

    def opt_int(v: Any) -> int | None:
        return int(v) if v is not None else None

    def opt_levels(v: Any) -> tuple[Decimal, ...]:
        if not v:
            return ()
        items = v if isinstance(v, (list, tuple)) else [v]
        return tuple(Decimal(str(i)) for i in items if i is not None)

    def safe_str(v: Any, default: str = "") -> str:
        return str(v) if v is not None else default

    price_ctx = PriceContext(
        current_price=to_decimal(price.get("current_price")),
        open_price=to_decimal(price.get("open_price")),
        high=to_decimal(price.get("high")),
        low=to_decimal(price.get("low")),
        prev_close=to_decimal(price.get("prev_close")) if price.get("prev_close") is not None else None,
        change_pct=to_decimal(price.get("change_pct")) if price.get("change_pct") is not None else None,
        volume=int(price.get("volume", 0)),
        avg_volume_20d=int(price.get("avg_volume_20d", 0)),
        avg_volume_10d=opt_int(price.get("avg_volume_10d")),
        avg_volume_5d=opt_int(price.get("avg_volume_5d")),
        circuit_status=CircuitStatus(safe_str(price.get("circuit_status"), "NORMAL")),
    )

    tech_ctx = TechnicalContext(
        rsi_14=to_decimal(tech.get("rsi_14")) if tech.get("rsi_14") is not None else None,
        macd=to_decimal(tech.get("macd")) if tech.get("macd") is not None else None,
        macd_signal=to_decimal(tech.get("macd_signal")) if tech.get("macd_signal") is not None else None,
        bb_upper=to_decimal(tech.get("bb_upper")) if tech.get("bb_upper") is not None else None,
        bb_lower=to_decimal(tech.get("bb_lower")) if tech.get("bb_lower") is not None else None,
        bb_width=to_decimal(tech.get("bb_width")) if tech.get("bb_width") is not None else None,
        ema_20=to_decimal(tech.get("ema_20")) if tech.get("ema_20") is not None else None,
        ema_50=to_decimal(tech.get("ema_50")) if tech.get("ema_50") is not None else None,
        ema_200=to_decimal(tech.get("ema_200")) if tech.get("ema_200") is not None else None,
        vwap=to_decimal(tech.get("vwap")) if tech.get("vwap") is not None else None,
        atr_14=to_decimal(tech.get("atr_14")) if tech.get("atr_14") is not None else None,
        support_levels=opt_levels(tech.get("support_levels")),
        resistance_levels=opt_levels(tech.get("resistance_levels")),
        supertrend_value=opt_decimal(tech.get("supertrend_value")),
        supertrend_direction=tech.get("supertrend_direction") or None,
        opening_15m_open=opt_decimal(tech.get("opening_15m_open")),
        opening_15m_high=opt_decimal(tech.get("opening_15m_high")),
        opening_15m_low=opt_decimal(tech.get("opening_15m_low")),
        opening_15m_close=opt_decimal(tech.get("opening_15m_close")),
        opening_15m_volume=opt_int(tech.get("opening_15m_volume")),
        opening_15m_avg_volume=opt_int(tech.get("opening_15m_avg_volume")),
        prev_day_high=opt_decimal(tech.get("prev_day_high")),
        prev_day_low=opt_decimal(tech.get("prev_day_low")),
    )

    breadth_ctx = BreadthContext(
        sector_index_change_pct=to_decimal(breadth.get("sector_index_change_pct")),
        sector_advance_decline=to_decimal(breadth.get("sector_advance_decline")),
        nifty_change_pct=to_decimal(breadth.get("nifty_change_pct")),
        sensex_change_pct=to_decimal(breadth.get("sensex_change_pct")),
    )

    news_ctx = NewsContext()

    dq_ctx = DataQuality(
        quality_score=float(dq.get("quality_score", 1.0)),
    )

    ts_str = packet_data.get("timestamp", "")
    ts = datetime.fromisoformat(ts_str) if ts_str else datetime.now()

    pkt = IntelligencePacket(
        symbol=packet_data.get("symbol", ""),
        timestamp=ts,
        freshness_validated=packet_data.get("freshness_validated", True),
        price_context=price_ctx,
        technical_context=tech_ctx,
        breadth_context=breadth_ctx,
        news_context=news_ctx,
        data_quality=dq_ctx,
        regime=packet_data.get("regime"),
    )

    return EnrichedIntelligencePacket(packet=pkt)


def _serialize_for_task(enriched: EnrichedIntelligencePacket) -> dict:
    from dataclasses import asdict
    from core.events.event_bus import _EventEncoder
    return json.loads(json.dumps(asdict(enriched), cls=_EventEncoder))


SUBSCRIBED_EVENTS: dict[str, list[Callable[[DomainEvent], None]]] = {
    "intelligence.PacketBuilt": [handle_enriched_packet],
}


def register_handlers(event_bus: EventBus) -> None:
    for event_type, handlers in SUBSCRIBED_EVENTS.items():
        for handler in handlers:
            event_bus.subscribe(
                event_type=event_type,
                handler=handler,
                consumer_group="rule_engine",
            )
