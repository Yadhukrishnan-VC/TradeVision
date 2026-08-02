from __future__ import annotations

from decimal import Decimal

from core.events.event_types import EventType, IntelligencePacket
from core.rules.base_rule import BaseRule, RuleResult, RuleSeverity


class VolatilityBreakoutRule(BaseRule):
    """SETUP 3 — Volatility Breakout.

    Deterministic breakout: the session's high-low range expands to at least
    1.5x ATR(14), AND the price breaks the previous trading day's high (long
    breakout) or low (short breakdown).

    ``event_type`` is intentionally dynamic per firing (``BREAKOUT`` for a
    long breakout, ``BREAKDOWN`` for a short breakdown), unlike the other
    rules whose event type is fixed — the ``RuleResult`` carries the
    direction-specific type.

    The trailing stop is Supertrend(10, 2), read as a pre-computed scalar
    from the packet (never recomputed here). If the payload did not supply
    ``supertrend_value``/``supertrend_direction``, the rule still fires on the
    deterministic entry conditions but reports ``supertrend_available=false``
    and fabricates no stop value. Missing ATR or previous-day H/L -> ``None``.
    """

    ATR_MULTIPLIER = Decimal("1.5")

    @property
    def rule_id(self) -> str:
        return "volatility_breakout_v1"

    @property
    def name(self) -> str:
        return "Volatility Breakout (Setup 3)"

    @property
    def event_type(self) -> EventType:
        return EventType.BREAKOUT

    @property
    def severity(self) -> RuleSeverity:
        return RuleSeverity.HIGH

    def evaluate(self, packet: IntelligencePacket) -> RuleResult | None:
        price = packet.price_context
        tech = packet.technical_context

        atr_14 = tech.atr_14
        prev_day_high = tech.prev_day_high
        prev_day_low = tech.prev_day_low
        if atr_14 is None or atr_14 <= 0:
            return None
        if prev_day_high is None or prev_day_low is None:
            return None

        session_high = price.high
        session_low = price.low
        if session_high is None or session_low is None:
            return None
        daily_range = session_high - session_low
        if daily_range < atr_14 * self.ATR_MULTIPLIER:
            return None

        current_price = price.current_price
        if current_price > prev_day_high:
            direction = "long"
        elif current_price < prev_day_low:
            direction = "short"
        else:
            return None

        event_type = (
            EventType.BREAKOUT if direction == "long" else EventType.BREAKDOWN
        )

        supertrend_value = tech.supertrend_value
        supertrend_direction = tech.supertrend_direction
        supertrend_available = (
            supertrend_value is not None and supertrend_direction is not None
        )

        trigger_data = {
            "setup": "volatility_breakout_v1",
            "entry_price": str(current_price),
            "atr_14": str(atr_14),
            "daily_range": str(daily_range),
            "prev_day_high": str(prev_day_high),
            "prev_day_low": str(prev_day_low),
            "direction": direction,
            "supertrend_value": str(supertrend_value) if supertrend_available else None,
            "supertrend_direction": supertrend_direction if supertrend_available else None,
            "supertrend_available": supertrend_available,
        }
        if supertrend_available:
            trigger_data["stop_loss"] = str(supertrend_value)
            trigger_data["stop_loss_basis"] = "supertrend_10_2"

        return RuleResult(
            rule_id=self.rule_id,
            event_type=event_type,
            severity=self.severity,
            trigger_data=trigger_data,
            description=(
                f"Volatility breakout {direction}: range {daily_range} "
                f">= 1.5x ATR {atr_14}"
            ),
        )
