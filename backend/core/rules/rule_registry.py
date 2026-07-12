"""
TradeVision AI — Rule registry.

Central registry that manages rule registration, lookup, and batch
evaluation. Uses ``BaseRule.safe_evaluate()`` to guarantee exception
safety during evaluation loops.
"""

import logging
from typing import Any

from core.events.event_types import IntelligencePacket
from core.exceptions import RuleEngineError
from core.rules.base_rule import BaseRule, RuleResult

logger = logging.getLogger(__name__)


class RuleRegistry:
    """
    Manages the set of active rules and dispatches evaluation.

    Usage::

        registry = RuleRegistry()
        registry.register(PriceMovementRule())
        results = registry.evaluate_all(packet)
    """

    def __init__(self) -> None:
        self._rules: dict[str, BaseRule] = {}

    def register(self, rule: BaseRule) -> None:
        """
        Register a rule instance.

        Raises:
            RuleEngineError: If a rule with the same ``rule_id`` is already registered.
        """
        if rule.rule_id in self._rules:
            raise RuleEngineError(
                f"Rule '{rule.rule_id}' is already registered. "
                "Unregister it first before re-registering."
            )
        self._rules[rule.rule_id] = rule
        logger.info(
            "rule_registered",
            extra={"rule_id": rule.rule_id, "rule_name": rule.name},
        )

    def unregister(self, rule_id: str) -> BaseRule:
        """
        Remove a rule by its ID.

        Returns:
            The removed rule instance.

        Raises:
            KeyError: If no rule with the given ID is registered.
        """
        rule = self._rules.pop(rule_id)
        logger.info("rule_unregistered", extra={"rule_id": rule_id})
        return rule

    def get_registered_rules(self) -> list[BaseRule]:
        """Return a list of all currently registered rules."""
        return list(self._rules.values())

    def evaluate_all(self, packet: IntelligencePacket) -> list[RuleResult]:
        """
        Evaluate all registered rules against the given IntelligencePacket.

        Uses ``safe_evaluate()`` to guarantee that no rule exception
        propagates upward. Returns a list of all ``RuleResult`` objects
        from rules that fired.
        """
        results: list[RuleResult] = []
        for rule in self._rules.values():
            result = rule.safe_evaluate(packet)
            if result is not None:
                results.append(result)
        return results

    def __len__(self) -> int:
        """Return the number of registered rules."""
        return len(self._rules)

    def __contains__(self, rule_id: str) -> bool:
        """Check if a rule with the given ID is registered."""
        return rule_id in self._rules
