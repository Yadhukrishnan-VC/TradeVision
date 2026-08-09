from __future__ import annotations

from decimal import Decimal

from core.events.event_types import EventType, IntelligencePacket
from core.rules.base_rule import BaseRule, RuleResult, RuleSeverity


class HighBetaBreakoutRule(BaseRule):
    """SETUP 4 — Intraday High Beta Breakout.

    Deterministic long entry: all three conditions must hold strictly —

      1. Relative volume: current candle volume > 2x the 5-day average
         daily volume.
      2. Bollinger breakout: close > the pre-computed BB(20, 2) upper band.
      3. RSI momentum: RSI(14) > 65.

    This rule is a pure, I/O-free function of the ``IntelligencePacket``. It
    never computes indicators or queries data; every value it reads was
    assembled upstream (payload-supplied BB-upper, TA-2 ``rsi_14``, and the
    session-facts-derived ``avg_volume_5d``). Missing or non-positive required
    data makes the rule return ``None`` (fail safe) — it never substitutes a
    default and never approves based on partial conditions.

    ``event_type`` is ``BREAKOUT`` so Risk Management's direction fallback
    resolves this long-only setup to ``long`` without any change to the frozen
    risk layer. No stop-loss basis is implied by the three entry conditions;
    following ``volatility_breakout_v1``'s documented precedent, the rule does
    not invent one — the missing ``stop_loss`` is surfaced to Risk Management
    for explicit rejection (``MISSING_STOP_LOSS``), never fabricated here.
    """

    VOLUME_MULTIPLIER = Decimal("2.0")
    RSI_THRESHOLD = Decimal("65.0")

    @property
    def rule_id(self) -> str:
        return "high_beta_breakout_v1"

    @property
    def name(self) -> str:
        return "High Beta Breakout (Setup 4)"

    @property
    def event_type(self) -> EventType:
        return EventType.BREAKOUT

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.HIGH

    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        price = packet.price_context
        tech = packet.technical_context

        current_price = price.current_price
        volume = price.volume

        avg_volume_5d = price.avg_volume_5d
        if avg_volume_5d is None or avg_volume_5d <= 0:
            return None
        if volume <= avg_volume_5d * self.VOLUME_MULTIPLIER:
            return None

        bb_upper = tech.bb_upper
        if bb_upper is None or current_price <= bb_upper:
            return None

        rsi_14 = tech.rsi_14
        if rsi_14 is None or rsi_14 <= self.RSI_THRESHOLD:
            return None

        volume_ratio = Decimal(str(volume)) / Decimal(str(avg_volume_5d))
        return RuleResult(
            rule_id=self.rule_id,
            event_type=self.event_type,
            severity=self.severity,
            trigger_data={
                "setup": "high_beta_breakout_v1",
                "entry_price": str(current_price),
                "volume": volume,
                "avg_volume_5d": avg_volume_5d,
                "volume_ratio": str(volume_ratio),
                "bb_upper": str(bb_upper),
                "rsi_14": str(rsi_14),
            },
            description=(
                f"High beta breakout: {volume_ratio:.1f}x 5d avg vol "
                f"({volume} vs {avg_volume_5d}), close {current_price} > "
                f"BB-upper {bb_upper}, RSI {rsi_14}"
            ),
        )