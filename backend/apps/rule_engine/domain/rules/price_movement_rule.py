from __future__ import annotations

from decimal import Decimal

from core.events.event_types import EventType, IntelligencePacket
from core.rules.base_rule import BaseRule, RuleResult, RuleSeverity


class PriceMovementRule(BaseRule):
    @property
    def rule_id(self) -> str:
        return "price_movement_v1"

    @property
    def name(self) -> str:
        return "Price Movement Rule"

    @property
    def event_type(self) -> EventType:
        return EventType.PRICE_MOVEMENT

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.HIGH

    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        threshold = Decimal("2.0")
        change = abs(packet.price_context.change_pct)
        if change >= threshold:
            return RuleResult(
                rule_id=self.rule_id,
                event_type=self.event_type,
                severity=self.severity,
                trigger_data={
                    "change_pct": str(packet.price_context.change_pct),
                    "threshold_pct": str(threshold),
                    "current_price": str(packet.price_context.current_price),
                },
                description=f"{packet.price_context.change_pct:+.2f}% price movement",
            )
        return None
