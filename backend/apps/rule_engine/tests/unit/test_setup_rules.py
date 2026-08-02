"""
Unit tests for the deterministic trading setups (SETUP 1-3).

Covers every deterministic condition, both stop-loss selection branches,
missing-data paths, and the pure-function / no-AI-import / no-execution
structural guarantees required by the M2 acceptance checklist.
"""

from __future__ import annotations

import inspect
import pathlib
from datetime import datetime, timezone
from decimal import Decimal

from apps.rule_engine.domain.rules import (
    LongMomentumRule,
    ShortSellRule,
    VolatilityBreakoutRule,
)
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

_RULE_MODULES = (
    pathlib.Path(inspect.getfile(LongMomentumRule)).parent
    / "long_momentum_rule.py",
    pathlib.Path(inspect.getfile(ShortSellRule)).parent
    / "short_sell_rule.py",
    pathlib.Path(inspect.getfile(VolatilityBreakoutRule)).parent
    / "volatility_breakout_rule.py",
)


def _make_packet(
    current_price: Decimal = Decimal("103.00"),
    open_price: Decimal = Decimal("100.00"),
    high: Decimal = Decimal("104.00"),
    low: Decimal = Decimal("99.50"),
    volume: int = 3_000_000,
    avg_volume_10d: int | None = 900_000,
    vwap: Decimal | None = Decimal("102.00"),
    ema_20: Decimal | None = Decimal("101.00"),
    atr_14: Decimal | None = None,
    prev_day_high: Decimal | None = None,
    prev_day_low: Decimal | None = None,
    opening_15m_open: Decimal | None = Decimal("100.00"),
    opening_15m_high: Decimal | None = Decimal("101.00"),
    opening_15m_low: Decimal | None = Decimal("100.00"),
    opening_15m_close: Decimal | None = Decimal("101.00"),
    opening_15m_volume: int | None = 600_000,
    opening_15m_avg_volume: int | None = 150_000,
    supertrend_value: Decimal | None = None,
    supertrend_direction: str | None = None,
    freshness_validated: bool = True,
) -> IntelligencePacket:
    return IntelligencePacket(
        symbol="RELIANCE",
        timestamp=datetime.now(timezone.utc),
        freshness_validated=freshness_validated,
        price_context=PriceContext(
            current_price=current_price,
            open_price=open_price,
            high=high,
            low=low,
            prev_close=Decimal("99.00"),
            change_pct=None,
            volume=volume,
            avg_volume_20d=900_000,
            avg_volume_10d=avg_volume_10d,
            circuit_status=CircuitStatus.NORMAL,
        ),
        technical_context=TechnicalContext(
            vwap=vwap,
            ema_20=ema_20,
            atr_14=atr_14,
            prev_day_high=prev_day_high,
            prev_day_low=prev_day_low,
            opening_15m_open=opening_15m_open,
            opening_15m_high=opening_15m_high,
            opening_15m_low=opening_15m_low,
            opening_15m_close=opening_15m_close,
            opening_15m_volume=opening_15m_volume,
            opening_15m_avg_volume=opening_15m_avg_volume,
            supertrend_value=supertrend_value,
            supertrend_direction=supertrend_direction,
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


class TestLongMomentumRule:
    def test_fires_on_valid_setup(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet()

        result = rule.evaluate(packet)

        assert result is not None
        assert result.rule_id == "long_momentum_v1"
        assert result.event_type == EventType.BREAKOUT
        assert result.severity == RuleSeverity.HIGH
        assert result.trigger_data["stop_loss_basis"] == "opening_15m_low"
        assert result.trigger_data["stop_loss"] == "100.00"

    def test_stop_loss_picks_vwap_when_lower(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet(
            vwap=Decimal("99.90"),
            opening_15m_open=Decimal("100.00"),
            opening_15m_low=Decimal("100.00"),
            current_price=Decimal("103.00"),
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert result.trigger_data["stop_loss_basis"] == "vwap"
        assert result.trigger_data["stop_loss"] == "99.90"

    def test_stop_loss_picks_opening_low_when_lower(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet(
            vwap=Decimal("102.00"),
            opening_15m_open=Decimal("99.80"),
            opening_15m_low=Decimal("99.80"),
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert result.trigger_data["stop_loss_basis"] == "opening_15m_low"
        assert result.trigger_data["stop_loss"] == "99.80"

    def test_does_not_fire_below_two_percent(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet(current_price=Decimal("101.90"))

        assert rule.evaluate(packet) is None

    def test_does_not_fire_on_insufficient_volume(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet(volume=2_699_999)

        assert rule.evaluate(packet) is None

    def test_does_not_fire_below_vwap(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet(vwap=Decimal("104.00"))

        assert rule.evaluate(packet) is None

    def test_does_not_fire_below_ema20(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet(ema_20=Decimal("105.00"))

        assert rule.evaluate(packet) is None

    def test_does_not_fire_when_open_not_equal_low(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet(
            opening_15m_open=Decimal("100.00"),
            opening_15m_low=Decimal("99.00"),
        )

        assert rule.evaluate(packet) is None

    def test_does_not_fire_when_avg_volume_10d_missing(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet(avg_volume_10d=None)

        assert rule.evaluate(packet) is None

    def test_does_not_fire_when_vwap_missing(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet(vwap=None)

        assert rule.evaluate(packet) is None

    def test_does_not_fire_when_opening_candle_missing(self) -> None:
        rule = LongMomentumRule()
        packet = _make_packet(opening_15m_open=None, opening_15m_low=None)

        assert rule.evaluate(packet) is None


class TestShortSellRule:
    def test_fires_on_valid_setup(self) -> None:
        rule = ShortSellRule()
        packet = _make_packet(
            current_price=Decimal("97.00"),
            open_price=Decimal("100.00"),
            high=Decimal("100.00"),
            low=Decimal("96.50"),
            vwap=Decimal("98.00"),
            ema_20=Decimal("98.50"),
            opening_15m_open=Decimal("100.00"),
            opening_15m_high=Decimal("100.00"),
            opening_15m_low=Decimal("98.50"),
            opening_15m_volume=600_000,
            opening_15m_avg_volume=150_000,
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert result.rule_id == "short_sell_v1"
        assert result.event_type == EventType.BREAKDOWN
        assert result.severity == RuleSeverity.HIGH
        assert result.trigger_data["stop_loss_basis"] == "opening_15m_high"
        assert result.trigger_data["stop_loss"] == "100.00"

    def test_stop_loss_picks_vwap_when_higher(self) -> None:
        rule = ShortSellRule()
        packet = _make_packet(
            current_price=Decimal("97.00"),
            open_price=Decimal("100.00"),
            vwap=Decimal("99.50"),
            ema_20=Decimal("99.00"),
            opening_15m_open=Decimal("99.00"),
            opening_15m_high=Decimal("99.00"),
            opening_15m_volume=600_000,
            opening_15m_avg_volume=150_000,
        )

        result = rule.evaluate(packet)

        assert result is not None
        assert result.trigger_data["stop_loss_basis"] == "vwap"
        assert result.trigger_data["stop_loss"] == "99.50"

    def test_does_not_fire_above_minus_two_percent(self) -> None:
        rule = ShortSellRule()
        packet = _make_packet(
            current_price=Decimal("98.10"),
            open_price=Decimal("100.00"),
            opening_15m_open=Decimal("100.00"),
            opening_15m_high=Decimal("100.00"),
            opening_15m_volume=600_000,
            opening_15m_avg_volume=150_000,
        )

        assert rule.evaluate(packet) is None

    def test_does_not_fire_on_insufficient_opening_volume(self) -> None:
        rule = ShortSellRule()
        packet = _make_packet(
            current_price=Decimal("97.00"),
            open_price=Decimal("100.00"),
            opening_15m_open=Decimal("100.00"),
            opening_15m_high=Decimal("100.00"),
            opening_15m_volume=450_000,
            opening_15m_avg_volume=150_000,
        )

        assert rule.evaluate(packet) is None

    def test_does_not_fire_above_vwap(self) -> None:
        rule = ShortSellRule()
        packet = _make_packet(
            current_price=Decimal("97.00"),
            open_price=Decimal("100.00"),
            vwap=Decimal("96.50"),
            ema_20=Decimal("98.50"),
            opening_15m_open=Decimal("100.00"),
            opening_15m_high=Decimal("100.00"),
            opening_15m_volume=600_000,
            opening_15m_avg_volume=150_000,
        )

        assert rule.evaluate(packet) is None

    def test_does_not_fire_when_open_not_equal_high(self) -> None:
        rule = ShortSellRule()
        packet = _make_packet(
            current_price=Decimal("97.00"),
            open_price=Decimal("100.00"),
            vwap=Decimal("98.00"),
            ema_20=Decimal("98.50"),
            opening_15m_open=Decimal("100.00"),
            opening_15m_high=Decimal("100.80"),
            opening_15m_volume=600_000,
            opening_15m_avg_volume=150_000,
        )

        assert rule.evaluate(packet) is None

    def test_does_not_fire_when_opening_volume_missing(self) -> None:
        rule = ShortSellRule()
        packet = _make_packet(
            current_price=Decimal("97.00"),
            open_price=Decimal("100.00"),
            opening_15m_open=Decimal("100.00"),
            opening_15m_high=Decimal("100.00"),
            opening_15m_volume=None,
            opening_15m_avg_volume=None,
        )

        assert rule.evaluate(packet) is None


class TestVolatilityBreakoutRule:
    def _breakout_packet(self, **kwargs):
        defaults = {
            "current_price": Decimal("112.00"),
            "high": Decimal("115.00"),
            "low": Decimal("100.00"),
            "atr_14": Decimal("10.00"),
            "prev_day_high": Decimal("110.00"),
            "prev_day_low": Decimal("95.00"),
        }
        defaults.update(kwargs)
        return _make_packet(**defaults)

    def test_fires_on_long_breakout(self) -> None:
        rule = VolatilityBreakoutRule()
        result = rule.evaluate(self._breakout_packet())

        assert result is not None
        assert result.rule_id == "volatility_breakout_v1"
        assert result.event_type == EventType.BREAKOUT
        assert result.trigger_data["direction"] == "long"
        assert result.trigger_data["daily_range"] == "15.00"

    def test_fires_on_short_breakdown(self) -> None:
        rule = VolatilityBreakoutRule()
        result = rule.evaluate(
            self._breakout_packet(current_price=Decimal("92.00"))
        )

        assert result is not None
        assert result.event_type == EventType.BREAKDOWN
        assert result.trigger_data["direction"] == "short"

    def test_fires_on_exact_atr_boundary(self) -> None:
        rule = VolatilityBreakoutRule()
        packet = self._breakout_packet(
            atr_14=Decimal("10.00"),
            high=Decimal("115.00"),
            low=Decimal("100.00"),
        )

        assert rule.evaluate(packet) is not None

    def test_does_not_fire_just_below_atr_boundary(self) -> None:
        rule = VolatilityBreakoutRule()
        packet = self._breakout_packet(
            atr_14=Decimal("10.01"),
            high=Decimal("115.00"),
            low=Decimal("100.00"),
        )

        assert rule.evaluate(packet) is None

    def test_does_not_fire_between_prev_day_hl(self) -> None:
        rule = VolatilityBreakoutRule()
        packet = self._breakout_packet(current_price=Decimal("105.00"))

        assert rule.evaluate(packet) is None

    def test_fires_without_supertrend_but_flags_unavailable(self) -> None:
        rule = VolatilityBreakoutRule()
        result = rule.evaluate(self._breakout_packet())

        assert result is not None
        assert result.trigger_data["supertrend_available"] is False
        assert result.trigger_data["supertrend_value"] is None
        assert "stop_loss" not in result.trigger_data

    def test_includes_supertrend_stop_when_available(self) -> None:
        rule = VolatilityBreakoutRule()
        result = rule.evaluate(
            self._breakout_packet(
                supertrend_value=Decimal("106.00"),
                supertrend_direction="up",
            )
        )

        assert result is not None
        assert result.trigger_data["supertrend_available"] is True
        assert result.trigger_data["supertrend_value"] == "106.00"
        assert result.trigger_data["supertrend_direction"] == "up"
        assert result.trigger_data["stop_loss_basis"] == "supertrend_10_2"
        assert result.trigger_data["stop_loss"] == "106.00"

    def test_does_not_fire_when_atr_missing(self) -> None:
        rule = VolatilityBreakoutRule()
        packet = self._breakout_packet(atr_14=None)

        assert rule.evaluate(packet) is None

    def test_does_not_fire_when_prev_day_hl_missing(self) -> None:
        rule = VolatilityBreakoutRule()
        packet = self._breakout_packet(prev_day_high=None, prev_day_low=None)

        assert rule.evaluate(packet) is None


class TestCrossCutting:
    def test_repeated_evaluation_is_identical(self) -> None:
        packet = _make_packet()
        for rule in (LongMomentumRule(), ShortSellRule(), VolatilityBreakoutRule()):
            first = rule.evaluate(packet)
            second = rule.evaluate(packet)
            assert first == second

    def test_setup_rules_never_import_ai_engine(self) -> None:
        for path in _RULE_MODULES:
            source = path.read_text()
            assert "ai_engine" not in source
            assert "core.ai" not in source
            assert "DeepSeekProvider" not in source
            assert "model_router" not in source

    def test_setup_rules_never_import_execution_broker(self) -> None:
        for path in _RULE_MODULES:
            source = path.read_text()
            assert "execute_order" not in source
            assert "broker" not in source
            assert "order_" not in source
