from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from apps.risk_management.domain.value_objects import RejectionReason


class RiskDecisionStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class RiskRejection:
    """Fail-closed rejection detail attached to a rejected decision."""

    code: RejectionReason
    message: str = ""


@dataclass(frozen=True)
class KillSwitchToggle:
    """A single kill-switch state change (on or off).

    Persisted to ``KillSwitchState`` and published as a domain event so the
    audit-log ``*`` subscriber records it for free.
    """

    scope: str
    symbol: str | None = None
    actor: str = "system"
    active: bool = True
    reason: str = ""
    toggled_at: datetime | None = None


@dataclass(frozen=True)
class RiskDecision:
    """A single fail-closed risk evaluation for a fired rule.

    Exactly one of ``approved``/``rejection`` semantics is carried: when
    ``status == APPROVED`` the sizing fields are populated and
    ``rejection`` is ``None``; when ``REJECTED`` the reverse holds.

    Attributes:
        symbol:                 Instrument symbol the rule fired for.
        rule_id:                Identifier of the originating rule.
        event_type:             Origin event type (BREAKOUT/BREAKDOWN).
        direction:              Position direction the rule opened (long/short).
        analysis_event_id:      Idempotency key, equal to the RuleFired
                                ``analysis_event_id`` (stable per stream entry).
        occurred_at:            When the decision was made (UTC).
        status:                 APPROVED or REJECTED.
        entry_price:            Filled entry price (Decimal).
        stop_loss:              Stop-loss level (Decimal).
        position_size:          Approved quantity, or 0 when rejected.
        risk_amount:            capital x risk_pct (Decimal).
        risk_pct_of_capital:    Fraction of capital risked on this trade.
        risk_reward_ratio:      R:R ratio (Decimal), 0 when no target.
        trigger_data:           The originating rule's trigger_data (audit).
        rejection:              RiskRejection when rejected, else None.
        reason_message:         Human-readable rejection detail (optional).
        portfolio_gateway_impl: Which gateway produced the capital/exposure
                                values (always "stub" in M3; guardrail).
    """

    symbol: str
    rule_id: str
    event_type: str
    analysis_event_id: UUID
    occurred_at: datetime
    status: RiskDecisionStatus
    direction: str = "long"
    entry_price: Decimal = Decimal(0)
    stop_loss: Decimal = Decimal(0)
    position_size: int = 0
    risk_amount: Decimal = Decimal(0)
    risk_pct_of_capital: Decimal = Decimal(0)
    risk_reward_ratio: Decimal = Decimal(0)
    trigger_data: dict = field(default_factory=dict)
    rejection: RiskRejection | None = None
    reason_message: str = ""
    portfolio_gateway_impl: str = "stub"
