"""
Tests for core/rules/rule_registry.py.

Uses concrete in-module rule subclasses to avoid importing business rules.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.events.event_types import (
    AggregateSentiment,
    BreadthContext,
    CircuitStatus,
    DataQuality,
    EventType,
    IntelligencePacket,
    NewsContext,
    PriceContext,
    TechnicalContext,
)
from core.exceptions import RuleConfigurationError
from core.rules.base_rule import BaseRule, RuleResult, RuleSeverity
from core.rules.rule_registry import RuleRegistry


# ---------------------------------------------------------------------------
# Test-only concrete rule implementations
# ---------------------------------------------------------------------------


class _AlwaysFiresRule(BaseRule):
    """Rule that unconditionally fires."""

    @property
    def rule_id(self) -> str:
        return "test_always_fires_v1"

    @property
    def name(self) -> str:
        return "Always Fires Rule"

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
            trigger_data={"symbol": packet.symbol},
            description="Unconditional fire",
        )


class _NeverFiresRule(BaseRule):
    """Rule that never fires."""

    @property
    def rule_id(self) -> str:
        return "test_never_fires_v1"

    @property
    def name(self) -> str:
        return "Never Fires Rule"

    @property
    def event_type(self) -> EventType:
        return EventType.VOLUME_SPIKE

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.LOW

    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        return None


class _RaisesExceptionRule(BaseRule):
    """Rule that raises a RuntimeError during evaluation."""

    @property
    def rule_id(self) -> str:
        return "test_raises_error_v1"

    @property
    def name(self) -> str:
        return "Error Rule"

    @property
    def event_type(self) -> EventType:
        return EventType.BREAKOUT

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.HIGH

    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        raise RuntimeError("Simulated evaluation error")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_packet(symbol: str = "TESTEQ") -> IntelligencePacket:
    """Build the minimal IntelligencePacket needed for rule evaluation."""
    return IntelligencePacket(
        symbol=symbol,
        timestamp=datetime.now(tz=timezone.utc),
        freshness_validated=True,
        price_context=PriceContext(
            current_price=Decimal("500.00"),
            open_price=Decimal("498.00"),
            high=Decimal("505.00"),
            low=Decimal("496.00"),
            prev_close=Decimal("499.00"),
            change_pct=Decimal("0.20"),
            volume=200_000,
            avg_volume_20d=150_000,
            circuit_status=CircuitStatus.NORMAL,
        ),
        technical_context=TechnicalContext(),
        breadth_context=BreadthContext(
            sector_index_change_pct=Decimal("0.15"),
            sector_advance_decline=Decimal("1.2"),
            nifty_change_pct=Decimal("0.10"),
            sensex_change_pct=Decimal("0.12"),
        ),
        news_context=NewsContext(),
        data_quality=DataQuality(),
    )


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestRuleRegistryRegistration:
    """register() and unregister() behaviour."""

    @pytest.fixture
    def registry(self) -> RuleRegistry:
        return RuleRegistry()

    def test_register_adds_rule(self, registry: RuleRegistry) -> None:
        rule = _AlwaysFiresRule()
        registry.register(rule)
        assert len(registry) == 1

    def test_get_registered_rules_returns_registered(
        self, registry: RuleRegistry
    ) -> None:
        rule = _AlwaysFiresRule()
        registry.register(rule)
        rules = registry.get_registered_rules()
        assert len(rules) == 1
        assert rules[0] is rule

    def test_register_multiple_rules(self, registry: RuleRegistry) -> None:
        registry.register(_AlwaysFiresRule())
        registry.register(_NeverFiresRule())
        assert len(registry) == 2

    def test_duplicate_rule_id_raises(self, registry: RuleRegistry) -> None:
        registry.register(_AlwaysFiresRule())
        with pytest.raises(RuleConfigurationError):
            registry.register(_AlwaysFiresRule())

    def test_unregister_removes_rule(self, registry: RuleRegistry) -> None:
        rule = _AlwaysFiresRule()
        registry.register(rule)
        registry.unregister(rule.rule_id)
        assert len(registry) == 0

    def test_unregister_nonexistent_raises(self, registry: RuleRegistry) -> None:
        with pytest.raises(RuleConfigurationError):
            registry.unregister("does_not_exist")

    def test_get_registered_rules_is_snapshot(self, registry: RuleRegistry) -> None:
        """Mutating the returned list must not affect the registry."""
        registry.register(_AlwaysFiresRule())
        snapshot = registry.get_registered_rules()
        snapshot.clear()
        assert len(registry) == 1

    def test_contains_registered_rule(self, registry: RuleRegistry) -> None:
        rule = _AlwaysFiresRule()
        registry.register(rule)
        assert rule.rule_id in registry

    def test_not_contains_unregistered_rule(self, registry: RuleRegistry) -> None:
        assert "not_registered_id" not in registry

    def test_len_empty_registry(self, registry: RuleRegistry) -> None:
        assert len(registry) == 0

    def test_repr_lists_rule_ids(self, registry: RuleRegistry) -> None:
        registry.register(_AlwaysFiresRule())
        assert "test_always_fires_v1" in repr(registry)


class TestRuleRegistryEvaluation:
    """evaluate_all() dispatches to safe_evaluate() and collects results."""

    @pytest.fixture
    def registry(self) -> RuleRegistry:
        return RuleRegistry()

    @pytest.fixture
    def packet(self) -> IntelligencePacket:
        return _make_packet()

    def test_evaluate_all_returns_only_fired_rules(
        self, registry: RuleRegistry, packet: IntelligencePacket
    ) -> None:
        registry.register(_AlwaysFiresRule())
        registry.register(_NeverFiresRule())
        results = registry.evaluate_all(packet)
        assert len(results) == 1
        assert results[0].rule_id == "test_always_fires_v1"

    def test_evaluate_all_empty_registry_returns_empty(
        self, registry: RuleRegistry, packet: IntelligencePacket
    ) -> None:
        results = registry.evaluate_all(packet)
        assert results == []

    def test_evaluate_all_isolates_exceptions(
        self, registry: RuleRegistry, packet: IntelligencePacket
    ) -> None:
        """An exception in one rule must not prevent others from running."""
        registry.register(_RaisesExceptionRule())
        registry.register(_AlwaysFiresRule())
        results = registry.evaluate_all(packet)
        assert len(results) == 1
        assert results[0].rule_id == "test_always_fires_v1"

    def test_evaluate_all_never_fires_returns_empty(
        self, registry: RuleRegistry, packet: IntelligencePacket
    ) -> None:
        registry.register(_NeverFiresRule())
        results = registry.evaluate_all(packet)
        assert results == []

    def test_evaluate_all_result_contains_trigger_data(
        self, registry: RuleRegistry, packet: IntelligencePacket
    ) -> None:
        registry.register(_AlwaysFiresRule())
        results = registry.evaluate_all(packet)
        assert results[0].trigger_data["symbol"] == "TESTEQ"
