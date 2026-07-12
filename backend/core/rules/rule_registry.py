"""
TradeVision AI — Rule engine registry.

Maintains the set of active market monitoring rules and orchestrates their
evaluation against an ``IntelligencePacket``. Thread-safe via a ``Lock``
so rules can be registered/unregistered while the evaluation loop runs.

Usage::

    registry = RuleRegistry()
    registry.register(PriceMovementRule())
    results = registry.evaluate_all(intelligence_packet)
"""

import logging
import threading

from core.events.event_types import IntelligencePacket
from core.exceptions import RuleConfigurationError
from core.rules.base_rule import BaseRule, RuleResult

logger = logging.getLogger(__name__)


class RuleRegistry:
    """
    Thread-safe registry for market monitoring rules.

    Rules are stored by ``rule_id`` (the unique identifier declared on each
    ``BaseRule`` subclass). Attempting to register a duplicate ``rule_id``
    raises ``RuleConfigurationError`` to prevent silent overwrites.

    ``evaluate_all()`` delegates to ``BaseRule.safe_evaluate()`` for every
    registered rule, which guarantees that exceptions inside individual rules
    never terminate the evaluation loop.
    """

    def __init__(self) -> None:
        self._rules: dict[str, BaseRule] = {}
        self._lock: threading.Lock = threading.Lock()

    def register(self, rule: BaseRule) -> None:
        """
        Add a rule to the registry.

        Args:
            rule: A concrete ``BaseRule`` instance to register.

        Raises:
            RuleConfigurationError: If a rule with the same ``rule_id`` is
                                    already registered.
        """
        with self._lock:
            if rule.rule_id in self._rules:
                raise RuleConfigurationError(
                    f"Rule '{rule.rule_id}' is already registered. "
                    "Call unregister() first if you intend to replace it."
                )
            self._rules[rule.rule_id] = rule

        logger.info(
            "rule_registered",
            extra={
                "rule_id": rule.rule_id,
                "rule_name": rule.name,
                "severity": rule.severity.value,
            },
        )

    def unregister(self, rule_id: str) -> None:
        """
        Remove a rule from the registry by its identifier.

        Args:
            rule_id: The ``rule_id`` of the rule to remove.

        Raises:
            RuleConfigurationError: If no rule with the given ``rule_id``
                                    is currently registered.
        """
        with self._lock:
            if rule_id not in self._rules:
                raise RuleConfigurationError(
                    f"Rule '{rule_id}' is not registered and cannot be unregistered."
                )
            del self._rules[rule_id]

        logger.info("rule_unregistered", extra={"rule_id": rule_id})

    def get_registered_rules(self) -> list[BaseRule]:
        """
        Return a snapshot of all currently registered rules.

        Returns a new list each call so callers cannot modify the registry's
        internal state through the returned collection.

        Returns:
            List of registered ``BaseRule`` instances in insertion order.
        """
        with self._lock:
            return list(self._rules.values())

    def evaluate_all(self, packet: IntelligencePacket) -> list[RuleResult]:
        """
        Evaluate every registered rule against the given IntelligencePacket.

        Uses ``BaseRule.safe_evaluate()`` which catches and logs all exceptions
        so that a bug in one rule never prevents other rules from running.

        Args:
            packet: The assembled IntelligencePacket for a specific symbol
                    at a specific point in time.

        Returns:
            List of ``RuleResult`` instances for every rule that fired.
            Rules that do not fire return ``None`` from ``safe_evaluate()``
            and are excluded from the results.
        """
        rules: list[BaseRule] = self.get_registered_rules()
        results: list[RuleResult] = []

        for rule in rules:
            result: RuleResult | None = rule.safe_evaluate(packet)
            if result is not None:
                results.append(result)

        logger.info(
            "rule_evaluation_complete",
            extra={
                "symbol": packet.symbol,
                "rules_evaluated": len(rules),
                "rules_fired": len(results),
                "fired_rule_ids": [r.rule_id for r in results],
            },
        )
        return results

    def __len__(self) -> int:
        """Return the number of currently registered rules."""
        with self._lock:
            return len(self._rules)

    def __contains__(self, rule_id: str) -> bool:
        """Return True if a rule with the given ID is registered."""
        with self._lock:
            return rule_id in self._rules

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        with self._lock:
            rule_ids = list(self._rules.keys())
        return f"<RuleRegistry rules={rule_ids}>"
