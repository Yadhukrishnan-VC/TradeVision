from __future__ import annotations

from decimal import Decimal

from core.events.event_types import EventType, IntelligencePacket
from core.rules.base_rule import BaseRule, RuleResult, RuleSeverity


class ShortBreakdownRule(BaseRule):
    """SETUP 6 — Short Breakdown.

    Deterministic short entry: all three conditions must hold strictly —

      1. Price below VWAP: current close < pre-computed VWAP.
      2. RSI momentum: RSI(14) < 35.
      3. Relative volume: current candle volume > 3x the 10-day average
         daily volume.

    This rule is a pure, I/O-free function of the ``IntelligencePacket``. It
    never computes indicators or queries data; every value it reads was
    assembled upstream (payload-supplied VWAP, TA-2 ``rsi_14``, and the
    session-facts-derived ``avg_volume_10d``). Missing or non-positive
    required data makes the rule return ``None`` (fail safe) — it never
    substitutes a default and never approves based on partial conditions.

    ``event_type`` is ``BREAKDOWN`` and ``trigger_data["direction"]`` is set
    explicitly to ``"short"`` (the same explicit-direction convention
    ``volatility_breakout_v1`` uses) so Risk Management's ``_infer_direction``
    resolves this short-only setup correctly without modifying the frozen
    risk layer. No stop-loss basis is implied by the three entry conditions;
    following the documented setup precedent, the rule does not invent one —
    the missing ``stop_loss`` is surfaced to Risk Management for explicit
    rejection (``MISSING_STOP_LOSS``), never fabricated here.
    """

    VOLUME_MULTIPLIER = Decimal("3.0")
    RSI_THRESHOLD = Decimal("35.0")

    @property
    def rule_id(self) -> str:
        return "short_breakdown_v1"

    @property
    def name(self) -> str:
        return "Short Breakdown (Setup 6)"

    @property
    def event_type(self) -> EventType:
        return EventType.BREAKDOWN

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.HIGH

    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        price = packet.price_context
        tech = packet.technical_context

        current_price = price.current_price
        volume = price.volume

        vwap = tech.vwap
        if vwap is None or current_price >= vwap:
            return None

        rsi_14 = tech.rsi_14
        if rsi_14 is None or rsi_14 >= self.RSI_THRESHOLD:
            return None

        avg_volume_10d = price.avg_volume_10d
        if avg_volume_10d is None or avg_volume_10d <= 0:
            return None
        if volume <= avg_volume_10d * self.VOLUME_MULTIPLIER:
            return None

        volume_ratio = Decimal(str(volume)) / Decimal(str(avg_volume_10d))
        return RuleResult(
            rule_id=self.rule_id,
            event_type=self.event_type,
            severity=self.severity,
            trigger_data={
                "setup": "short_breakdown_v1",
                "direction": "short",
                "entry_price": str(current_price),
                "volume": volume,
                "avg_volume_10d": avg_volume_10d,
                "volume_ratio": str(volume_ratio),
                "vwap": str(vwap),
                "rsi_14": str(rsi_14),
            },
            description=(
                f"Short breakdown: close {current_price} below VWAP {vwap}, "
                f"RSI {rsi_14}, {volume_ratio:.1f}x 10d avg vol "
                f"({volume} vs {avg_volume_10d})"
            ),
        )