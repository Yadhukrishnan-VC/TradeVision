from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.risk_management.domain.entities import RiskDecision
from apps.risk_management.domain.value_objects import KillSwitchScope, RejectionReason


@dataclass(frozen=True)
class RiskApproved:
    """Payload for ``risk_management.RiskApproved``.

    ``correlation_id``/``causation_id`` are attached by the publisher:
    correlation = RuleFired.analysis_event_id, causation = RuleFired.event_id.
    """

    symbol: str
    rule_id: str
    event_type: str
    entry_price: Decimal
    stop_loss: Decimal
    position_size: int
    risk_amount: Decimal
    risk_pct_of_capital: Decimal
    risk_reward_ratio: Decimal
    # Risk-engine computed direction ("long"/"short"). "" means "not carried"
    # (legacy/external producers); execution falls back to the static rule
    # sets in that case, preserving pre-EXEC-1 behavior.
    direction: str = ""
    portfolio_gateway_impl: str = "stub"

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "rule_id": self.rule_id,
            "event_type": self.event_type,
            "direction": self.direction,
            "entry_price": str(self.entry_price),
            "stop_loss": str(self.stop_loss),
            "position_size": self.position_size,
            "risk_amount": str(self.risk_amount),
            "risk_pct_of_capital": str(self.risk_pct_of_capital),
            "risk_reward_ratio": str(self.risk_reward_ratio),
            "portfolio_gateway_impl": self.portfolio_gateway_impl,
        }

    @classmethod
    def from_decision(cls, decision: RiskDecision) -> RiskApproved:
        return cls(
            symbol=decision.symbol,
            rule_id=decision.rule_id,
            event_type=decision.event_type,
            direction=decision.direction,
            entry_price=decision.entry_price,
            stop_loss=decision.stop_loss,
            position_size=decision.position_size,
            risk_amount=decision.risk_amount,
            risk_pct_of_capital=decision.risk_pct_of_capital,
            risk_reward_ratio=decision.risk_reward_ratio,
            portfolio_gateway_impl=decision.portfolio_gateway_impl,
        )


@dataclass(frozen=True)
class RiskRejected:
    """Payload for ``risk_management.RiskRejected`` (no position_size)."""

    symbol: str
    rule_id: str
    event_type: str
    reason_code: RejectionReason
    reason_message: str
    portfolio_gateway_impl: str = "stub"

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "rule_id": self.rule_id,
            "event_type": self.event_type,
            "reason_code": self.reason_code.value,
            "reason_message": self.reason_message,
            "portfolio_gateway_impl": self.portfolio_gateway_impl,
        }

    @classmethod
    def from_decision(cls, decision: RiskDecision) -> RiskRejected:
        code = decision.rejection.code if decision.rejection else RejectionReason.UNKNOWN
        return cls(
            symbol=decision.symbol,
            rule_id=decision.rule_id,
            event_type=decision.event_type,
            reason_code=code,
            reason_message=decision.reason_message,
            portfolio_gateway_impl=decision.portfolio_gateway_impl,
        )


@dataclass(frozen=True)
class KillSwitchActivated:
    """Payload for ``risk_management.KillSwitchActivated``."""

    scope: KillSwitchScope
    symbol: str | None
    actor: str
    reason: str
    activated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "symbol": self.symbol,
            "actor": self.actor,
            "reason": self.reason,
            "activated_at": self.activated_at.isoformat(),
        }


@dataclass(frozen=True)
class KillSwitchDeactivated:
    """Payload for ``risk_management.KillSwitchDeactivated``."""

    scope: KillSwitchScope
    symbol: str | None
    actor: str
    reason: str
    deactivated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "symbol": self.symbol,
            "actor": self.actor,
            "reason": self.reason,
            "deactivated_at": self.deactivated_at.isoformat(),
        }
