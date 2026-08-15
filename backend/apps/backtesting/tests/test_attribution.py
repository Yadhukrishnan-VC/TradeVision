"""Batch M4.5 — Per-rule trade attribution (pure helpers + repository)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.backtesting.domain.attribution import (
    build_correlation_to_rule_map,
    group_fills_by_rule,
)


def _execution(event_id, rule_id):
    return SimpleNamespace(analysis_event_id=event_id, rule_id=rule_id)


def _order(order_id, correlation_id):
    return SimpleNamespace(id=order_id, correlation_id=correlation_id)


def _fill(order_id):
    return SimpleNamespace(order_id=order_id)


class TestBuildCorrelationToRuleMap:
    def test_maps_event_ids_to_rule_ids(self):
        mapping = build_correlation_to_rule_map(
            [
                _execution("evt-a", "long_momentum_v1"),
                _execution("evt-b", "breakout_v1"),
            ]
        )
        assert mapping == {"evt-a": "long_momentum_v1", "evt-b": "breakout_v1"}

    def test_accepts_uuid_style_ids_via_str(self):
        event_id = "550e8400-e29b-41d4-a716-446655440000"
        mapping = build_correlation_to_rule_map([_execution(event_id, "short_v1")])
        assert mapping["550e8400-e29b-41d4-a716-446655440000"] == "short_v1"

    def test_first_row_wins_for_multiple_rules_per_event(self):
        mapping = build_correlation_to_rule_map(
            [
                _execution("evt-a", "breakout_v1"),
                _execution("evt-a", "long_momentum_v1"),
            ]
        )
        assert mapping == {"evt-a": "breakout_v1"}

    def test_empty_input_returns_empty_map(self):
        assert build_correlation_to_rule_map([]) == {}


class TestGroupFillsByRule:
    def test_groups_fills_by_rule_via_order_correlation(self):
        order = _order("order-1", "evt-a")
        fills = [_fill("order-1"), _fill("order-1")]
        by_rule = group_fills_by_rule(
            fills,
            [_execution("evt-a", "long_momentum_v1")],
            order_by_id={"order-1": order},
        )
        assert by_rule == {"long_momentum_v1": fills}

    def test_excludes_fills_with_no_matching_rule(self):
        attributed = _order("order-1", "evt-a")
        unattributed = _order("order-2", "evt-unknown")
        fills = [_fill("order-1"), _fill("order-2")]
        by_rule = group_fills_by_rule(
            fills,
            [_execution("evt-a", "long_momentum_v1")],
            order_by_id={"order-1": attributed, "order-2": unattributed},
        )
        assert by_rule == {"long_momentum_v1": [_fill("order-1")]}
        assert len(fills) - sum(len(v) for v in by_rule.values()) == 1

    def test_missing_order_is_not_attributed(self):
        fills = [_fill("order-missing")]
        by_rule = group_fills_by_rule(
            fills,
            [_execution("evt-a", "long_momentum_v1")],
            order_by_id={},
        )
        assert by_rule == {}

    def test_falls_back_to_fill_order_when_no_map_provided(self):
        order = _order("order-1", "evt-a")
        fill = _fill("order-1")
        fill.order = order
        by_rule = group_fills_by_rule(fills=[fill], rule_executions=[_execution("evt-a", "x")])
        assert by_rule == {"x": [fill]}

    def test_unattributed_count_equals_remaining_fills(self):
        order = _order("order-1", "evt-a")
        fills = [_fill("order-1")]
        by_rule = group_fills_by_rule(fills, [_execution("evt-a", "r")], {"order-1": order})
        assert len(fills) - sum(len(v) for v in by_rule.values()) == 0


@pytest.mark.django_db
def test_rule_attribution_repository_joins_on_analysis_event_id():
    from apps.rule_engine.infrastructure.models import RuleExecution

    evt_a = "550e8400-e29b-41d4-a716-446655440000"
    evt_b = "550e8400-e29b-41d4-a716-446655440001"

    RuleExecution.objects.create(
        analysis_event_id=evt_a,
        rule_id="long_momentum_v1",
        symbol="RELIANCE",
        severity="medium",
    )
    RuleExecution.objects.create(
        analysis_event_id=evt_b,
        rule_id="breakout_v1",
        symbol="RELIANCE",
        severity="high",
    )

    from apps.backtesting.infrastructure.rule_attribution_repository import (
        RuleAttributionRepository,
    )

    repo = RuleAttributionRepository()
    rows = repo.get_rule_executions({evt_a})
    assert [(row.analysis_event_id, row.rule_id) for row in rows] == [
        (uuid.UUID(evt_a), "long_momentum_v1")
    ]

    assert repo.get_rule_executions(set()) == []
    assert repo.get_rule_executions({"550e8400-e29b-41d4-a716-44665544ffff"}) == []
