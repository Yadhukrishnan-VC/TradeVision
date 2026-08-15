"""Pure rule-attribution helpers for backtest trade breakdowns (Batch M4.5).

Every backtest Order carries the same ``correlation_id`` as the analysis
event (one per historical bar) that produced it, and that id is stored as
``RuleExecution.analysis_event_id``. A Fill is traced back to the rule that
ultimately caused it through its (non-null) ``Order`` FK:

    Fill -> Order.correlation_id -> RuleExecution.analysis_event_id -> rule_id

These helpers are deliberately pure — no ORM, no Django imports. Callers
fetch the ``RuleExecution`` rows once and pass them in; the only attribute
reads are on already-fetched fill/order/rule-execution objects.
"""

from __future__ import annotations

from typing import Any


def build_correlation_to_rule_map(rule_executions: list[Any]) -> dict[str, str]:
    """Map each ``RuleExecution.analysis_event_id`` to its ``rule_id``.

    Keys are normalized to ``str`` so the map is safe regardless of whether
    callers hand in UUID objects or strings. When several rules fire for one
    analysis event (multiple rules on the same bar), the first row wins —
    the same deterministic tie-break ``_resolve_regimes`` relies on, given
    the repository returns rows newest-first by default.
    """
    mapping: dict[str, str] = {}
    for execution in rule_executions:
        event_id = execution.analysis_event_id
        key = str(event_id)
        if key not in mapping:
            mapping[key] = execution.rule_id
    return mapping


def group_fills_by_rule(
    fills: list[Any],
    rule_executions: list[Any],
    order_by_id: dict[str, Any] | None = None,
) -> dict[str, list[Any]]:
    """Group fills under the ``rule_id`` that produced each one.

    Args:
        fills: ``Fill`` rows for one backtest run (already fetched).
        rule_executions: ``RuleExecution`` rows for the run's correlation ids
            (already fetched, e.g. via ``RuleAttributionRepository``).
        order_by_id: Optional pre-built ``{str(order.id): order}`` map to
            avoid per-fill ORM lookups on ``fill.order``.

    Returns:
        ``{rule_id: [fill, ...]}`` for fills whose order's ``correlation_id``
        matches a rule execution. Fills that trace to no rule are excluded;
        their count is ``len(fills) - sum(len(v) for v in by_rule.values())``.
    """
    correlation_to_rule = build_correlation_to_rule_map(rule_executions)
    by_rule: dict[str, list[Any]] = {}
    for fill in fills:
        order = (
            order_by_id.get(str(fill.order_id))
            if order_by_id is not None
            else fill.order
        )
        if order is None:
            continue
        rule_id = correlation_to_rule.get(str(order.correlation_id))
        if rule_id is not None:
            by_rule.setdefault(rule_id, []).append(fill)
    return by_rule
