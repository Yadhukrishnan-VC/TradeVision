from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    DataQuality,
    EventType,
    IntelligencePacket,
    NewsContext,
    PriceContext,
    TechnicalContext,
)
from core.rules.base_rule import RuleSeverity
from apps.rule_engine.domain.rules import (
    BreakoutRule,
    PriceMovementRule,
    VolumeSpikeRule,
)


def _make_packet(
    symbol: str = "TEST",
    change_pct: Decimal = Decimal("0.00"),
    volume: int = 100_000,
    avg_volume_20d: int = 100_000,
    current_price: Decimal = Decimal("100.00"),
    bb_upper: Decimal | None = None,
    resistance_levels: tuple[Decimal, ...] = (),
) -> IntelligencePacket:
    return IntelligencePacket(
        symbol=symbol,
        timestamp=datetime.now(timezone.utc),
        freshness_validated=True,
        price_context=PriceContext(
            current_price=current_price,
            open_price=Decimal("99.00"),
            high=Decimal("101.00"),
            low=Decimal("98.50"),
            prev_close=Decimal("99.50"),
            change_pct=change_pct,
            volume=volume,
            avg_volume_20d=avg_volume_20d,
            circuit_status=CircuitStatus.NORMAL,
        ),
        technical_context=TechnicalContext(
            bb_upper=bb_upper,
            bb_lower=Decimal("95.00"),
            resistance_levels=resistance_levels,
        ),
        breadth_context=BreadthContext(
            sector_index_change_pct=Decimal("0.00"),
            sector_advance_decline=Decimal("0.00"),
            nifty_change_pct=Decimal("0.00"),
            sensex_change_pct=Decimal("0.00"),
        ),
        news_context=NewsContext(),
        data_quality=DataQuality(quality_score=1.0),
    )


class TestPriceMovementRule:
    def test_fires_on_positive_change_above_threshold(self) -> None:
        rule = PriceMovementRule()
        packet = _make_packet(change_pct=Decimal("3.50"))

        result = rule.evaluate(packet)

        assert result is not None
        assert result.rule_id == "price_movement_v1"
        assert result.event_type == EventType.PRICE_MOVEMENT
        assert result.severity == RuleSeverity.HIGH
        assert "change_pct" in result.trigger_data

    def test_fires_on_negative_change_above_threshold(self) -> None:
        rule = PriceMovementRule()
        packet = _make_packet(change_pct=Decimal("-3.50"))

        result = rule.evaluate(packet)

        assert result is not None
        assert "change_pct" in result.trigger_data

    def test_fires_on_exact_threshold(self) -> None:
        rule = PriceMovementRule()
        packet = _make_packet(change_pct=Decimal("2.00"))

        result = rule.evaluate(packet)

        assert result is not None

    def test_does_not_fire_below_threshold(self) -> None:
        rule = PriceMovementRule()
        packet = _make_packet(change_pct=Decimal("1.99"))

        result = rule.evaluate(packet)

        assert result is None

    def test_does_not_fire_on_small_negative_change(self) -> None:
        rule = PriceMovementRule()
        packet = _make_packet(change_pct=Decimal("-1.50"))

        result = rule.evaluate(packet)

        assert result is None

    def test_does_not_fire_on_zero_change(self) -> None:
        rule = PriceMovementRule()
        packet = _make_packet(change_pct=Decimal("0.00"))

        result = rule.evaluate(packet)

        assert result is None

    def test_trigger_data_contains_change_pct(self) -> None:
        rule = PriceMovementRule()
        packet = _make_packet(change_pct=Decimal("5.25"))

        result = rule.evaluate(packet)

        assert result is not None
        assert result.trigger_data["change_pct"] == "5.25"
        assert result.trigger_data["threshold_pct"] == "2.0"
        assert result.trigger_data["current_price"] == "100.00"

    def test_description_format(self) -> None:
        rule = PriceMovementRule()
        packet = _make_packet(change_pct=Decimal("3.50"))

        result = rule.evaluate(packet)

        assert result is not None
        assert "3.50% price movement" in result.description


class TestVolumeSpikeRule:
    def test_fires_on_volume_above_threshold(self) -> None:
        rule = VolumeSpikeRule()
        packet = _make_packet(volume=1_000_000, avg_volume_20d=200_000)

        result = rule.evaluate(packet)

        assert result is not None
        assert result.rule_id == "volume_spike_v1"
        assert result.event_type == EventType.VOLUME_SPIKE
        assert result.severity == RuleSeverity.MEDIUM

    def test_fires_on_exact_threshold(self) -> None:
        rule = VolumeSpikeRule()
        packet = _make_packet(volume=250_000, avg_volume_20d=100_000)

        result = rule.evaluate(packet)

        assert result is not None

    def test_does_not_fire_below_threshold(self) -> None:
        rule = VolumeSpikeRule()
        packet = _make_packet(volume=240_000, avg_volume_20d=100_000)

        result = rule.evaluate(packet)

        assert result is None

    def test_does_not_fire_on_normal_volume(self) -> None:
        rule = VolumeSpikeRule()
        packet = _make_packet(volume=100_000, avg_volume_20d=100_000)

        result = rule.evaluate(packet)

        assert result is None

    def test_does_not_fire_when_avg_volume_is_zero(self) -> None:
        rule = VolumeSpikeRule()
        packet = _make_packet(volume=1_000_000, avg_volume_20d=0)

        result = rule.evaluate(packet)

        assert result is None

    def test_trigger_data_contains_volume_info(self) -> None:
        rule = VolumeSpikeRule()
        packet = _make_packet(volume=1_000_000, avg_volume_20d=200_000)

        result = rule.evaluate(packet)

        assert result is not None
        assert result.trigger_data["volume"] == 1_000_000
        assert result.trigger_data["avg_volume_20d"] == 200_000
        assert result.trigger_data["ratio"] == "5.0"
        assert result.trigger_data["threshold_multiplier"] == "2.5"

    def test_description_format(self) -> None:
        rule = VolumeSpikeRule()
        packet = _make_packet(volume=1_000_000, avg_volume_20d=200_000)

        result = rule.evaluate(packet)

        assert result is not None
        assert "5.0x average" in result.description


class TestBreakoutRule:
    def test_fires_on_bb_upper_break(self) -> None:
        rule = BreakoutRule()
        packet = _make_packet(
            current_price=Decimal("101.00"),
            bb_upper=Decimal("100.00"),
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert result.rule_id == "breakout_v1"
        assert result.event_type == EventType.BREAKOUT
        assert result.severity == RuleSeverity.HIGH
        assert "bb_upper_break" in result.trigger_data
        assert "resistance_level" not in result.trigger_data

    def test_fires_on_resistance_break(self) -> None:
        rule = BreakoutRule()
        packet = _make_packet(
            current_price=Decimal("101.00"),
            resistance_levels=(Decimal("100.00"),),
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert "resistance_break" in result.trigger_data
        assert "bb_upper_break" not in result.trigger_data

    def test_fires_on_both_bb_upper_and_resistance_break(self) -> None:
        rule = BreakoutRule()
        packet = _make_packet(
            current_price=Decimal("101.00"),
            bb_upper=Decimal("100.00"),
            resistance_levels=(Decimal("100.00"),),
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert "bb_upper_break" in result.trigger_data
        assert "resistance_break" in result.trigger_data

    def test_fires_when_price_equals_bb_upper(self) -> None:
        rule = BreakoutRule()
        packet = _make_packet(
            current_price=Decimal("100.00"),
            bb_upper=Decimal("100.00"),
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert "bb_upper_break" in result.trigger_data
        assert result.trigger_data["bb_upper_break"] == "0.00"

    def test_fires_when_price_equals_resistance(self) -> None:
        rule = BreakoutRule()
        packet = _make_packet(
            current_price=Decimal("100.00"),
            resistance_levels=(Decimal("100.00"),),
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert "resistance_break" in result.trigger_data
        assert result.trigger_data["resistance_break"] == "0.00"

    def test_does_not_fire_below_bb_upper_and_resistance(self) -> None:
        rule = BreakoutRule()
        packet = _make_packet(
            current_price=Decimal("99.00"),
            bb_upper=Decimal("100.00"),
            resistance_levels=(Decimal("100.00"),),
        )

        result = rule.evaluate(packet)

        assert result is None

    def test_does_not_fire_with_no_resistance_levels_and_no_bb(self) -> None:
        rule = BreakoutRule()
        packet = _make_packet(current_price=Decimal("100.00"))

        result = rule.evaluate(packet)

        assert result is None

    def test_uses_latest_resistance_level(self) -> None:
        rule = BreakoutRule()
        packet = _make_packet(
            current_price=Decimal("101.00"),
            resistance_levels=(Decimal("95.00"), Decimal("100.00")),
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert "resistance_break" in result.trigger_data
        assert result.trigger_data["resistance_level"] == "100.00"

    def test_description_format(self) -> None:
        rule = BreakoutRule()
        packet = _make_packet(
            current_price=Decimal("101.00"),
            bb_upper=Decimal("100.00"),
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert "Breakout detected at 101.00" in result.description
