from __future__ import annotations

import pytest

from apps.execution.domain.exceptions import UnknownRuleError
from apps.execution.domain.value_objects import resolve_side, side_for_rule
from apps.portfolio.domain.value_objects import Side


class TestSideForRule:
    def test_long_rules_map_to_long(self) -> None:
        assert side_for_rule("long_momentum_v1") is Side.LONG
        # A bidirectional rule defaults to long only in the static fallback;
        # the risk-engine direction on RiskApproved takes precedence.
        assert side_for_rule("volatility_breakout_v1") is Side.LONG

    def test_short_rule_maps_to_short(self) -> None:
        assert side_for_rule("short_sell_v1") is Side.SHORT

    def test_unknown_rule_raises(self) -> None:
        with pytest.raises(UnknownRuleError):
            side_for_rule("no_such_rule")


class TestResolveSide:
    def test_explicit_long_wins_for_bidirectional_rule(self) -> None:
        assert resolve_side("volatility_breakout_v1", "long") is Side.LONG

    def test_explicit_short_wins_for_bidirectional_rule(self) -> None:
        assert resolve_side("volatility_breakout_v1", "short") is Side.SHORT

    def test_explicit_long_for_long_only_rule(self) -> None:
        assert resolve_side("long_momentum_v1", "long") is Side.LONG

    def test_missing_direction_falls_back_to_static_sets(self) -> None:
        assert resolve_side("long_momentum_v1", None) is Side.LONG
        assert resolve_side("volatility_breakout_v1", None) is Side.LONG
        assert resolve_side("short_sell_v1", None) is Side.SHORT

    def test_empty_direction_falls_back_to_static_sets(self) -> None:
        assert resolve_side("short_sell_v1", "") is Side.SHORT

    def test_unrecognised_direction_falls_back_to_static_sets(self) -> None:
        assert resolve_side("long_momentum_v1", "sideways") is Side.LONG

    def test_unknown_rule_with_missing_direction_raises(self) -> None:
        with pytest.raises(UnknownRuleError):
            resolve_side("no_such_rule", None)

    def test_unknown_rule_with_unrecognised_direction_raises(self) -> None:
        with pytest.raises(UnknownRuleError):
            resolve_side("no_such_rule", "sideways")
