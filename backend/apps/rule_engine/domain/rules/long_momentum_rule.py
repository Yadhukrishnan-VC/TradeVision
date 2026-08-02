from __future__ import annotations

from decimal import Decimal

from core.events.event_types import EventType, IntelligencePacket
from core.rules.base_rule import BaseRule, RuleResult, RuleSeverity


class LongMomentumRule(BaseRule):
    """SETUP 1 — Long Momentum.

    Deterministic long entry: the price is up more than 2% from the session
    open on at least 3x the 10-day average volume, holds above VWAP and
    EMA20, and the opening candle printed "Open = Low".

    This rule is a pure, I/O-free function of the ``IntelligencePacket``. It
    never computes indicators or queries data; all values it reads were
    assembled upstream (payload-supplied VWAP/EMA20, session-facts-derived
    opening candle and 10-day average volume). Missing required data makes
    the rule return ``None`` (fail safe) — it never substitutes a default.
    """

    CHANGE_FROM_OPEN_PCT = Decimal("2.0")
    VOLUME_MULTIPLIER = Decimal("3.0")
    OPEN_EQUALS_LOW_TOLERANCE = Decimal("0.05")

    @property
    def rule_id(self) -> str:
        return "long_momentum_v1"

    @property
    def name(self) -> str:
        return "Long Momentum (Setup 1)"

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

        # Session open: prefer the true 09:15 opening-candle open when the
        # session-facts enrichment populated it, else fall back to the payload
        # `open` field (whose semantics are the alert-firing bar's open).
        session_open = tech.opening_15m_open or price.open_price
        if session_open is None or session_open == 0:
            return None

        change_pct = (current_price - session_open) / session_open * Decimal(100)
        if change_pct <= self.CHANGE_FROM_OPEN_PCT:
            return None

        avg_volume_10d = price.avg_volume_10d
        if avg_volume_10d is None or avg_volume_10d <= 0:
            return None
        if volume <= avg_volume_10d * self.VOLUME_MULTIPLIER:
            return None

        vwap = tech.vwap
        ema_20 = tech.ema_20
        opening_open = tech.opening_15m_open
        opening_low = tech.opening_15m_low
        if vwap is None or ema_20 is None or opening_open is None or opening_low is None:
            return None

        if current_price <= vwap:
            return None
        if current_price <= ema_20:
            return None
        if abs(opening_open - opening_low) > self.OPEN_EQUALS_LOW_TOLERANCE:
            return None

        stop_loss = min(opening_low, vwap)
        stop_loss_basis = "opening_15m_low" if opening_low <= vwap else "vwap"

        volume_ratio = Decimal(str(volume)) / Decimal(str(avg_volume_10d))
        return RuleResult(
            rule_id=self.rule_id,
            event_type=self.event_type,
            severity=self.severity,
            trigger_data={
                "setup": "long_momentum_v1",
                "change_pct": str(change_pct),
                "volume": volume,
                "avg_volume_10d": avg_volume_10d,
                "volume_ratio": str(volume_ratio),
                "vwap": str(vwap),
                "ema_20": str(ema_20),
                "opening_15m_open": str(opening_open),
                "opening_15m_low": str(opening_low),
                "stop_loss": str(stop_loss),
                "stop_loss_basis": stop_loss_basis,
            },
            description=(
                f"Long momentum: +{change_pct:.2f}% from open, "
                f"above VWAP and EMA20, SL {stop_loss} ({stop_loss_basis})"
            ),
        )
