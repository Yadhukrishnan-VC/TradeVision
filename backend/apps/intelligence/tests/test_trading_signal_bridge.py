from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from apps.eventbus.domain.events import DomainEvent
from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    DataQuality,
    IntelligencePacket,
    NewsContext,
    PriceContext,
    TechnicalContext,
)


class TestTradingSignalBridge:
    def test_price_context_optional_fields_default_to_none(self) -> None:
        ctx = PriceContext(
            current_price=Decimal("0"),
            open_price=Decimal("0"),
            high=Decimal("0"),
            low=Decimal("0"),
            prev_close=None,
            change_pct=None,
            volume=0,
            avg_volume_20d=0,
            circuit_status=CircuitStatus.NORMAL,
        )
        assert ctx.prev_close is None
        assert ctx.change_pct is None

    def test_intelligence_packet_with_optional_none_fields(self) -> None:
        packet = IntelligencePacket(
            symbol="TEST",
            timestamp=datetime.now(timezone.utc),
            freshness_validated=True,
            price_context=PriceContext(
                current_price=Decimal("100.00"),
                open_price=Decimal("99.00"),
                high=Decimal("101.00"),
                low=Decimal("98.50"),
                prev_close=None,
                change_pct=None,
                volume=100000,
                avg_volume_20d=50000,
                circuit_status=CircuitStatus.NORMAL,
            ),
            technical_context=TechnicalContext(),
            breadth_context=BreadthContext(
                sector_index_change_pct=Decimal("0.00"),
                sector_advance_decline=Decimal("0.00"),
                nifty_change_pct=Decimal("0.00"),
                sensex_change_pct=Decimal("0.00"),
            ),
            news_context=NewsContext(),
            data_quality=DataQuality(),
        )
        assert packet.price_context.prev_close is None
        assert packet.price_context.change_pct is None
