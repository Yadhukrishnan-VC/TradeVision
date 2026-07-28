from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    DataQuality,
    EnrichedIntelligencePacket,
    IntelligencePacket,
    NewsContext,
    PriceContext,
    TechnicalContext,
)


@pytest.fixture
def correlation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def symbol() -> str:
    return "RELIANCE"


@pytest.fixture
def analysis_event_id() -> uuid.UUID:
    return uuid.uuid4()


def make_price_context(
    current_price: Decimal = Decimal("2500.00"),
    open_price: Decimal = Decimal("2480.00"),
    high: Decimal = Decimal("2520.00"),
    low: Decimal = Decimal("2470.00"),
    prev_close: Decimal = Decimal("2450.00"),
    change_pct: Decimal = Decimal("2.04"),
    volume: int = 1_500_000,
    avg_volume_20d: int = 500_000,
    circuit_status: CircuitStatus = CircuitStatus.NORMAL,
) -> PriceContext:
    return PriceContext(
        current_price=current_price,
        open_price=open_price,
        high=high,
        low=low,
        prev_close=prev_close,
        change_pct=change_pct,
        volume=volume,
        avg_volume_20d=avg_volume_20d,
        circuit_status=circuit_status,
    )


def make_technical_context(
    rsi_14: Decimal | None = None,
    macd: Decimal | None = None,
    macd_signal: Decimal | None = None,
    bb_upper: Decimal | None = None,
    bb_lower: Decimal | None = None,
    ema_20: Decimal | None = None,
    ema_50: Decimal | None = None,
    ema_200: Decimal | None = None,
    vwap: Decimal | None = None,
    resistance_levels: tuple[Decimal, ...] = (),
    **kwargs: Any,
) -> TechnicalContext:
    return TechnicalContext(
        rsi_14=rsi_14,
        macd=macd,
        macd_signal=macd_signal,
        bb_upper=bb_upper,
        bb_lower=bb_lower,
        ema_20=ema_20,
        ema_50=ema_50,
        ema_200=ema_200,
        vwap=vwap,
        resistance_levels=resistance_levels,
        **kwargs,
    )


def make_breadth_context(
    sector_index_change_pct: Decimal = Decimal("0.50"),
    sector_advance_decline: Decimal = Decimal("0.30"),
    nifty_change_pct: Decimal = Decimal("0.40"),
    sensex_change_pct: Decimal = Decimal("0.30"),
) -> BreadthContext:
    return BreadthContext(
        sector_index_change_pct=sector_index_change_pct,
        sector_advance_decline=sector_advance_decline,
        nifty_change_pct=nifty_change_pct,
        sensex_change_pct=sensex_change_pct,
    )


def make_intelligence_packet(
    symbol: str = "RELIANCE",
    change_pct: Decimal = Decimal("2.04"),
    volume: int = 1_500_000,
    avg_volume_20d: int = 500_000,
    current_price: Decimal = Decimal("2500.00"),
    bb_upper: Decimal | None = None,
    resistance_levels: tuple[Decimal, ...] = (),
    freshness_validated: bool = True,
    **price_kwargs: Any,
) -> IntelligencePacket:
    return IntelligencePacket(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        freshness_validated=freshness_validated,
        price_context=make_price_context(
            current_price=current_price,
            change_pct=change_pct,
            volume=volume,
            avg_volume_20d=avg_volume_20d,
            **price_kwargs,
        ),
        technical_context=make_technical_context(
            bb_upper=bb_upper,
            resistance_levels=resistance_levels,
        ),
        breadth_context=make_breadth_context(),
        news_context=NewsContext(),
        data_quality=DataQuality(quality_score=1.0),
    )


def make_enriched_packet(packet: IntelligencePacket) -> EnrichedIntelligencePacket:
    return EnrichedIntelligencePacket(packet=packet)


@pytest.fixture
def price_movement_packet(symbol: str) -> EnrichedIntelligencePacket:
    packet = make_intelligence_packet(
        symbol=symbol,
        change_pct=Decimal("3.50"),
        current_price=Decimal("2535.75"),
    )
    return make_enriched_packet(packet)


@pytest.fixture
def volume_spike_packet(symbol: str) -> EnrichedIntelligencePacket:
    packet = make_intelligence_packet(
        symbol=symbol,
        volume=2_000_000,
        avg_volume_20d=500_000,
        change_pct=Decimal("0.50"),
    )
    return make_enriched_packet(packet)


@pytest.fixture
def breakout_packet(symbol: str) -> EnrichedIntelligencePacket:
    packet = make_intelligence_packet(
        symbol=symbol,
        current_price=Decimal("2560.00"),
        bb_upper=Decimal("2550.00"),
        resistance_levels=(Decimal("2520.00"),),
        change_pct=Decimal("1.50"),
    )
    return make_enriched_packet(packet)


@pytest.fixture
def multi_fire_packet(symbol: str) -> EnrichedIntelligencePacket:
    packet = make_intelligence_packet(
        symbol=symbol,
        change_pct=Decimal("3.50"),
        volume=2_000_000,
        avg_volume_20d=500_000,
        current_price=Decimal("2560.00"),
        bb_upper=Decimal("2550.00"),
        resistance_levels=(Decimal("2520.00"),),
    )
    return make_enriched_packet(packet)


@pytest.fixture
def no_fire_packet(symbol: str) -> EnrichedIntelligencePacket:
    packet = make_intelligence_packet(
        symbol=symbol,
        change_pct=Decimal("0.50"),
        volume=600_000,
        avg_volume_20d=500_000,
        current_price=Decimal("2460.00"),
        bb_upper=Decimal("2600.00"),
        resistance_levels=(Decimal("2600.00"),),
    )
    return make_enriched_packet(packet)


@pytest.fixture
def stale_packet(symbol: str) -> EnrichedIntelligencePacket:
    packet = make_intelligence_packet(
        symbol=symbol,
        freshness_validated=False,
    )
    return make_enriched_packet(packet)
