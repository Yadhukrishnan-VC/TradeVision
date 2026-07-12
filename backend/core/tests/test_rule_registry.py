"""
Tests for RuleRegistry — register, unregister, evaluate_all.
"""

import pytest

from core.events.event_types import EventType, IntelligencePacket, PriceContext, TechnicalContext, BreadthContext, NewsContext, DataQuality
from core.exceptions import RuleEngineError
from core.rules.base_rule import BaseRule, RuleResult, RuleSeverity
from core.rules.rule_registry import RuleRegistry
from datetime import datetime, timezone
from decimal import Decimal


class _DummyRule(BaseRule):
    """A rule that always fires for testing."""

    @property
    def rule_id(self) -> str:
        return "dummy_rule"

    @property
    def name(self) -> str:
        return "Dummy Rule"

    @property
    def event_type(self) -> EventType:
        return EventType.PRICE_MOVEMENT

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.LOW

    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        return RuleResult(
            rule_id=self.rule_id,
            event_type=self.event_type,
            severity=self.severity,
            trigger_data={"test": "true"},
            description="Dummy rule fired",
        )


class _SilentRule(BaseRule):
    """A rule that never fires for testing."""

    @property
    def rule_id(self) -> str:
        return "silent_rule"

    @property
    def name(self) -> str:
        return "Silent Rule"

    @property
    def event_type(self) -> EventType:
        return EventType.VOLUME_SPIKE

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.HIGH

    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        return None


def _make_packet() -> IntelligencePacket:
    """Create a minimal IntelligencePacket for testing."""
    return IntelligencePacket(
        symbol="TEST",
        timestamp=datetime.now(tz=timezone.utc),
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
            circuit_status="NORMAL",
        ),
        technical_context=TechnicalContext(),
        breadth_context=BreadthContext(
            sector_index_change_pct=Decimal("0.5"),
            sector_advance_decline=Decimal("1.2"),
            nifty_change_pct=Decimal("0.3"),
            sensex_change_pct=Decimal("0.2"),
        ),
        news_context=NewsContext(),
        data_quality=DataQuality(),
    )


class TestRuleRegistry:

    def test_register_and_get(self) -> None:
        reg = RuleRegistry()
        rule = _DummyRule()
        reg.register(rule)
        assert "dummy_rule" in reg
        assert len(reg) == 1

    def test_duplicate_register_raises(self) -> None:
        reg = RuleRegistry()
        reg.register(_DummyRule())
        with pytest.raises(RuleEngineError):
            reg.register(_DummyRule())

    def test_unregister(self) -> None:
        reg = RuleRegistry()
        reg.register(_DummyRule())
        removed = reg.unregister("dummy_rule")
        assert removed.rule_id == "dummy_rule"
        assert len(reg) == 0

    def test_unregister_unknown_raises(self) -> None:
        reg = RuleRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nonexistent")

    def test_evaluate_all_dispatches(self) -> None:
        reg = RuleRegistry()
        reg.register(_DummyRule())
        reg.register(_SilentRule())
        results = reg.evaluate_all(_make_packet())
        assert len(results) == 1
        assert results[0].rule_id == "dummy_rule"
