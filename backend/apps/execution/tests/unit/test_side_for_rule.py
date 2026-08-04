from __future__ import annotations

import pytest

from apps.execution.domain.exceptions import UnknownRuleError
from apps.execution.domain.value_objects import side_for_rule
from apps.portfolio.domain.value_objects import Side


class TestSideForRule:
    def test_long_rules_map_to_long(self) -> None:
        assert side_for_rule("long_momentum_v1") is Side.LONG
        assert side_for_rule("volatility_breakout_v1") is Side.LONG

    def test_short_rule_maps_to_short(self) -> None:
        assert side_for_rule("short_sell_v1") is Side.SHORT

    def test_unknown_rule_raises(self) -> None:
        with pytest.raises(UnknownRuleError):
            side_for_rule("no_such_rule")
