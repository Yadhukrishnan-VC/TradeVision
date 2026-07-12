"""
Tests for core.events.event_types — frozen immutability, naive datetime rejection.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.events.event_types import (
    AnalysisEvent,
    DataQuality,
    EventType,
    IntelligencePacket,
    PriceContext,
    TechnicalContext,
    BreadthContext,
    NewsContext,
    CircuitStatus,
)


class TestFrozenImmutability:

    def test_price_context_is_frozen(self) -> None:
        pc = PriceContext(
            current_price=Decimal("100"),
            open_price=Decimal("99"),
            high=Decimal("101"),
            low=Decimal("98"),
            prev_close=Decimal("99"),
            change_pct=Decimal("1.01"),
            volume=100000,
            avg_volume_20d=80000,
            circuit_status=CircuitStatus.NORMAL,
        )
        with pytest.raises(AttributeError):
            pc.current_price = Decimal("200")


class TestNaiveDatetimeRejection:

    def test_intelligence_packet_rejects_naive(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            IntelligencePacket(
                symbol="TEST",
                timestamp=datetime(2024, 3, 13, 10, 0),  # naive
                freshness_validated=True,
                price_context=PriceContext(
                    current_price=Decimal("100"),
                    open_price=Decimal("99"),
                    high=Decimal("101"),
                    low=Decimal("98"),
                    prev_close=Decimal("99"),
                    change_pct=Decimal("1.01"),
                    volume=100000,
                    avg_volume_20d=80000,
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

    def test_analysis_event_rejects_naive(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            AnalysisEvent(
                id=uuid.uuid4(),
                event_type=EventType.PRICE_MOVEMENT,
                symbol="TEST",
                timestamp=datetime(2024, 3, 13, 10, 0),  # naive
                rule_id="test_rule",
            )


class TestDataQualityDefaults:

    def test_default_score(self) -> None:
        dq = DataQuality()
        assert dq.quality_score == 1.0

    def test_missing_sources_default(self) -> None:
        dq = DataQuality()
        assert dq.missing_sources == ()
