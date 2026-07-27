"""
Round-trip test for the intelligence enrichment pipeline.

Verifies that an IntelligencePacket with all optional blocks populated
survives ``_packet_to_json → _deserialise_packet`` with every field intact.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from apps.intelligence.infrastructure.event_consumers import (
    PortfolioRiskContextBuilder,
)
from core.events.event_bus import _EventEncoder
from core.events.event_types import (
    AggregateSentiment,
    AnnouncementContext,
    AnnouncementItem,
    BreadthContext,
    CircuitStatus,
    DataQuality,
    Deal,
    EnrichedIntelligencePacket,
    GlobalContext,
    InstitutionalContext,
    IntelligencePacket,
    MarketTrend,
    MaterialityLevel,
    NewsContext,
    NewsItem,
    OptionsContext,
    PatternContext,
    PatternMatch,
    PendingEvent,
    PriceContext,
    TechnicalContext,
)


# ---------------------------------------------------------------------------
# Fixture — fully populated IntelligencePacket
# ---------------------------------------------------------------------------


def _make_full_packet() -> IntelligencePacket:
    ts = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)

    return IntelligencePacket(
        symbol="RELIANCE",
        timestamp=ts,
        freshness_validated=True,
        price_context=PriceContext(
            current_price=Decimal("2850.50"),
            open_price=Decimal("2840.00"),
            high=Decimal("2865.00"),
            low=Decimal("2835.00"),
            prev_close=Decimal("2840.00"),
            change_pct=Decimal("0.37"),
            volume=5_000_000,
            avg_volume_20d=4_200_000,
            circuit_status=CircuitStatus.NORMAL,
        ),
        technical_context=TechnicalContext(
            trend=MarketTrend.UPTREND,
            rsi_14=Decimal("62.5"),
            macd=Decimal("12.30"),
            macd_signal=Decimal("11.80"),
            macd_histogram=Decimal("0.50"),
            bb_upper=Decimal("2900.00"),
            bb_lower=Decimal("2800.00"),
            bb_width=Decimal("3.5"),
            vwap=Decimal("2845.00"),
            atr_14=Decimal("45.00"),
            ema_20=Decimal("2830.00"),
            ema_50=Decimal("2800.00"),
            ema_200=Decimal("2700.00"),
            support_levels=(Decimal("2800"), Decimal("2750")),
            resistance_levels=(Decimal("2900"), Decimal("2950")),
        ),
        breadth_context=BreadthContext(
            sector_index_change_pct=Decimal("0.25"),
            sector_advance_decline=Decimal("0.40"),
            nifty_change_pct=Decimal("0.15"),
            sensex_change_pct=Decimal("0.12"),
        ),
        news_context=NewsContext(
            headlines=(
                NewsItem(
                    title="Reliance Q2 beats estimates",
                    source="Reuters",
                    sentiment=AggregateSentiment.POSITIVE,
                    materiality=MaterialityLevel.HIGH,
                    age_minutes=15,
                    url="https://example.com/reliance-q2",
                ),
            ),
            aggregate_sentiment=AggregateSentiment.POSITIVE,
        ),
        data_quality=DataQuality(
            quality_score=0.95,
            missing_sources=(),
            stale_sources=("options",),
        ),
        # --- optional enrichment blocks ---
        options_context=OptionsContext(
            pcr=Decimal("1.20"),
            max_pain=Decimal("2850"),
            atm_iv=Decimal("18.5"),
            oi_change_pct=Decimal("3.2"),
            unusual_activity=True,
        ),
        announcement_context=AnnouncementContext(
            recent_announcements=(
                AnnouncementItem(
                    announcement_type="earnings",
                    title="Q2 FY27 Results",
                    materiality=MaterialityLevel.HIGH,
                    age_hours=2.5,
                ),
            ),
            pending_events=(
                PendingEvent(
                    event_type="dividend",
                    scheduled_at=datetime(2026, 8, 15, 0, 0, tzinfo=timezone.utc),
                ),
            ),
        ),
        global_context=GlobalContext(
            dow_futures_pct=Decimal("-0.10"),
            sgx_nifty_pct=Decimal("0.05"),
            crude_oil_pct=Decimal("-0.50"),
            usd_inr_change_pct=Decimal("0.02"),
            vix=Decimal("14.5"),
            india_vix=Decimal("13.2"),
            fii_net_flow_cr=Decimal("850.00"),
        ),
        institutional_context=InstitutionalContext(
            bulk_deals=(
                Deal(
                    entity="Mukesh Ambani Trust",
                    quantity=500_000,
                    price=Decimal("2850.00"),
                    side="BUY",
                ),
            ),
            block_deals=(
                Deal(
                    entity="Goldman Sachs",
                    quantity=200_000,
                    price=Decimal("2845.00"),
                    side="SELL",
                ),
            ),
        ),
        pattern_context=PatternContext(
            similar_dates=(
                PatternMatch(
                    date_str="2024-03-17",
                    similarity_score=Decimal("0.87"),
                    outcome_summary="Price rose 2.1% over next 5 sessions",
                ),
            ),
            top_analogue_summary="Today resembles 17 Mar 2024 at 87% similarity",
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialise(packet: IntelligencePacket) -> dict:
    return json.loads(
        json.dumps(dataclasses.asdict(packet), cls=_EventEncoder)
    )


def _assert_packets_equal(
    original: IntelligencePacket,
    reconstructed: IntelligencePacket,
) -> None:
    """Assert every field matches, with a clear diff on failure."""

    def _sort_nested(val: object) -> object:
        if isinstance(val, tuple):
            return tuple(sorted(_sort_nested(v) for v in val))
        if isinstance(val, dict):
            return {k: _sort_nested(v) for k, v in val.items()}
        return val

    left = dataclasses.asdict(original)
    right = dataclasses.asdict(reconstructed)

    # Walk all keys recursively
    _walk_and_assert(left, right, path="")


def _walk_and_assert(left: object, right: object, path: str) -> None:
    if isinstance(left, (int, float, str, bool, type(None))):
        assert left == right, f"Mismatch at {path}: {left!r} != {right!r}"
    elif isinstance(left, Decimal):
        assert right is None or isinstance(right, Decimal)
        if right is not None:
            assert left == right, f"Mismatch at {path}: {left} != {right}"
    elif isinstance(left, list):
        assert isinstance(right, list), f"Type mismatch at {path}"
        assert len(left) == len(right), f"Length mismatch at {path}"
        for i, (lv, rv) in enumerate(zip(left, right)):
            _walk_and_assert(lv, rv, f"{path}[{i}]")
    elif isinstance(left, dict):
        assert isinstance(right, dict), f"Type mismatch at {path}"
        assert left.keys() == right.keys(), f"Keys differ at {path}: {left.keys()} vs {right.keys()}"
        for k in left:
            _walk_and_assert(left[k], right[k], f"{path}.{k}")
    elif isinstance(left, tuple):
        _walk_and_assert(list(left), list(right), path)
    else:
        assert left == right, f"Mismatch at {path}: {left!r} != {right!r}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIntelligencePacketRoundTrip:
    """Round-trip: ``_packet_to_json → _deserialise_packet`` preserves all fields."""

    def test_every_field_survives_deserialisation(self) -> None:
        original = _make_full_packet()
        serialised = _serialise(original)

        builder = PortfolioRiskContextBuilder(MagicMock())
        reconstructed = builder._deserialise_packet(serialised)

        _assert_packets_equal(original, reconstructed)

    def test_required_fields_when_optional_blocks_are_none(self) -> None:
        """Even when optional blocks are None, required 8 fields survive."""
        ts = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)
        original = IntelligencePacket(
            symbol="TEST",
            timestamp=ts,
            freshness_validated=True,
            price_context=PriceContext(
                current_price=Decimal("100"),
                open_price=Decimal("99"),
                high=Decimal("101"),
                low=Decimal("98"),
                prev_close=Decimal("99"),
                change_pct=Decimal("1.01"),
                volume=1_000_000,
                avg_volume_20d=800_000,
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
        serialised = _serialise(original)
        builder = PortfolioRiskContextBuilder(MagicMock())
        reconstructed = builder._deserialise_packet(serialised)

        assert reconstructed.options_context is None
        assert reconstructed.announcement_context is None
        assert reconstructed.global_context is None
        assert reconstructed.institutional_context is None
        assert reconstructed.pattern_context is None

        assert isinstance(reconstructed.news_context, NewsContext)
        assert reconstructed.news_context.headlines == ()
        assert reconstructed.news_context.aggregate_sentiment == AggregateSentiment.NEUTRAL

    def test_enriched_packet_round_trip_with_all_blocks(self) -> None:
        """Full pipeline: packet → serialise → _deserialise_packet → EnrichedIntelligencePacket."""
        original_packet = _make_full_packet()
        serialised = _serialise(original_packet)

        builder = PortfolioRiskContextBuilder(MagicMock())
        reconstructed_packet = builder._deserialise_packet(serialised)

        enriched = EnrichedIntelligencePacket(
            packet=reconstructed_packet,
            portfolio_context=None,
            risk_context=None,
        )

        # Re-serialise the enriched packet to confirm JSON round-trip
        enriched_serialised = json.loads(
            json.dumps(dataclasses.asdict(enriched), cls=_EventEncoder)
        )
        enriched_rehydrated = enriched_serialised["packet"]

        # Deserialise the inner packet again
        final_packet = builder._deserialise_packet(enriched_rehydrated)
        _assert_packets_equal(original_packet, final_packet)
