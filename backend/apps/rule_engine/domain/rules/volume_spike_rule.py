from __future__ import annotations

from decimal import Decimal

from core.events.event_types import EventType, IntelligencePacket
from core.rules.base_rule import BaseRule, RuleResult, RuleSeverity


class VolumeSpikeRule(BaseRule):
    VOLUME_THRESHOLD_MULTIPLIER = Decimal("2.5")

    @property
    def rule_id(self) -> str:
        return "volume_spike_v1"

    @property
    def name(self) -> str:
        return "Volume Spike Rule"

    @property
    def event_type(self) -> EventType:
        return EventType.VOLUME_SPIKE

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.MEDIUM

    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        volume = packet.price_context.volume
        avg_volume = packet.price_context.avg_volume_20d
        if avg_volume <= 0:
            return None
        ratio = Decimal(str(volume)) / Decimal(str(avg_volume))
        if ratio >= self.VOLUME_THRESHOLD_MULTIPLIER:
            return RuleResult(
                rule_id=self.rule_id,
                event_type=self.event_type,
                severity=self.severity,
                trigger_data={
                    "volume": volume,
                    "avg_volume_20d": avg_volume,
                    "ratio": str(ratio),
                    "threshold_multiplier": str(self.VOLUME_THRESHOLD_MULTIPLIER),
                },
                description=f"Volume spike: {ratio:.1f}x average ({volume} vs {avg_volume})",
            )
        return None
