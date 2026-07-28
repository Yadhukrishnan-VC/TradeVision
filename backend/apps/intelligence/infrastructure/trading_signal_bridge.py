from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from apps.eventbus.domain.events import DomainEvent
from apps.intelligence.services import MarketContextService, SignalContextRef
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


def handle_signal_created(event: DomainEvent) -> None:
    payload = event.payload
    symbol = payload.get("symbol", "")
    if not symbol:
        logger.warning("signal_created_missing_symbol", extra={"event_id": str(event.event_id)})
        return

    service = MarketContextService()
    packet = IntelligencePacket(
        symbol=symbol,
        timestamp=event.occurred_at,
        freshness_validated=True,
        price_context=PriceContext(
            current_price=Decimal("0"),
            open_price=Decimal("0"),
            high=Decimal("0"),
            low=Decimal("0"),
            prev_close=Decimal("0"),
            change_pct=Decimal("0"),
            volume=0,
            avg_volume_20d=0,
            circuit_status=CircuitStatus.NORMAL,
        ),
        technical_context=TechnicalContext(),
        breadth_context=BreadthContext(
            sector_index_change_pct=Decimal("0"),
            sector_advance_decline=Decimal("0"),
            nifty_change_pct=Decimal("0"),
            sensex_change_pct=Decimal("0"),
        ),
        news_context=NewsContext(),
        data_quality=DataQuality(),
    )

    signal_ref = None
    signal_id_str = payload.get("signal_id")
    if signal_id_str:
        signal_ref = SignalContextRef(
            signal_id=uuid.UUID(signal_id_str),
            direction=payload.get("direction", "WAIT"),
            confidence_hint=float(payload.get("confidence_hint", 0.0)),
        )

    context = service.build_signal_context(
        symbol=symbol,
        packet=packet,
        trading_signal=signal_ref,
    )
    logger.info(
        "signal_context_triggered_by_bridge",
        extra={
            "signal_id": payload.get("signal_id"),
            "symbol": symbol,
            "direction": payload.get("direction"),
        },
    )
    return context
