from __future__ import annotations

from decimal import Decimal

from core.events.event_types import EventType, IntelligencePacket
from core.rules.base_rule import BaseRule, RuleResult, RuleSeverity


class ShortSellRule(BaseRule):
    """SETUP 2 — Short Sell.

    Deterministic short entry: the price is down more than 2% from the
    session open with high-volume selling in the opening 15 minutes
    (>= 3x the trailing opening-15m average volume), holds below VWAP and
    EMA20, and the opening candle printed "Open = High".

    Pure and I/O-free: all values are read from the upstream-assembled
    packet (payload VWAP/EMA20, session-facts opening-15m volume and
    trailing baseline). Missing required data -> ``None`` (fail safe).
    """

    CHANGE_FROM_OPEN_PCT = Decimal("2.0")
    OPENING_VOLUME_MULTIPLIER = Decimal("3.0")
    OPEN_EQUALS_HIGH_TOLERANCE = Decimal("0.05")

    @property
    def rule_id(self) -> str:
        return "short_sell_v1"

    @property
    def name(self) -> str:
        return "Short Sell (Setup 2)"

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

        session_open = tech.opening_15m_open or price.open_price
        if session_open is None or session_open == 0:
            return None

        change_pct = (current_price - session_open) / session_open * Decimal(100)
        if change_pct >= -self.CHANGE_FROM_OPEN_PCT:
            return None

        opening_volume = tech.opening_15m_volume
        opening_avg_volume = tech.opening_15m_avg_volume
        if opening_volume is None or opening_avg_volume is None or opening_avg_volume <= 0:
            return None
        if opening_volume <= opening_avg_volume * self.OPENING_VOLUME_MULTIPLIER:
            return None

        vwap = tech.vwap
        ema_20 = tech.ema_20
        opening_open = tech.opening_15m_open
        opening_high = tech.opening_15m_high
        if vwap is None or ema_20 is None or opening_open is None or opening_high is None:
            return None

        if current_price >= vwap:
            return None
        if current_price >= ema_20:
            return None
        if abs(opening_open - opening_high) > self.OPEN_EQUALS_HIGH_TOLERANCE:
            return None

        stop_loss = max(opening_high, vwap)
        stop_loss_basis = "opening_15m_high" if opening_high >= vwap else "vwap"

        volume_ratio = Decimal(str(opening_volume)) / Decimal(str(opening_avg_volume))
        return RuleResult(
            rule_id=self.rule_id,
            event_type=self.event_type,
            severity=self.severity,
            trigger_data={
                "setup": "short_sell_v1",
                "change_pct": str(change_pct),
                "opening_15m_volume": opening_volume,
                "opening_15m_avg_volume": opening_avg_volume,
                "volume_ratio": str(volume_ratio),
                "vwap": str(vwap),
                "ema_20": str(ema_20),
                "opening_15m_open": str(opening_open),
                "opening_15m_high": str(opening_high),
                "stop_loss": str(stop_loss),
                "stop_loss_basis": stop_loss_basis,
            },
            description=(
                f"Short sell: {change_pct:.2f}% from open, "
                f"below VWAP and EMA20, SL {stop_loss} ({stop_loss_basis})"
            ),
        )
