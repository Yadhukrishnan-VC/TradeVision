from __future__ import annotations

from decimal import Decimal

from core.events.event_types import EventType, IntelligencePacket
from core.rules.base_rule import BaseRule, RuleResult, RuleSeverity


class BreakoutRule(BaseRule):
    @property
    def rule_id(self) -> str:
        return "breakout_v1"

    @property
    def name(self) -> str:
        return "Breakout Rule"

    @property
    def event_type(self) -> EventType:
        return EventType.BREAKOUT

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.HIGH

    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        tech = packet.technical_context
        price = packet.price_context.current_price
        bb_upper = tech.bb_upper
        resistance = (
            tech.resistance_levels[-1] if tech.resistance_levels else None
        )
        triggered = False
        trigger_data = {}

        if bb_upper is not None and price >= bb_upper:
            triggered = True
            trigger_data["bb_upper_break"] = str(price - bb_upper)
            trigger_data["bb_upper"] = str(bb_upper)

        if resistance is not None and price >= resistance:
            triggered = True
            trigger_data["resistance_break"] = str(price - resistance)
            trigger_data["resistance_level"] = str(resistance)

        if triggered:
            return RuleResult(
                rule_id=self.rule_id,
                event_type=self.event_type,
                severity=self.severity,
                trigger_data=trigger_data,
                description=f"Breakout detected at {price}",
            )
        return None
