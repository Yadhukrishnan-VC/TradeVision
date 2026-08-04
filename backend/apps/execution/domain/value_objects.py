from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from apps.execution.domain.exceptions import UnknownRuleError
from apps.portfolio.domain.value_objects import Side

# Rule -> direction mapping. Mirrors the M3 risk engine's rule sets
# (_LONG_RULES / _SHORT_RULES) so execution derives the position side from
# the rule that fired; the RiskApproved payload carries no side field.
_LONG_RULES: frozenset[str] = frozenset({"long_momentum_v1", "volatility_breakout_v1"})
_SHORT_RULES: frozenset[str] = frozenset({"short_sell_v1"})


def side_for_rule(rule_id: str) -> Side:
    """Map a configured rule id to the position direction it opens."""
    if rule_id in _LONG_RULES:
        return Side.LONG
    if rule_id in _SHORT_RULES:
        return Side.SHORT
    raise UnknownRuleError(rule_id)


class OrderStatus(str, Enum):
    """Internal order lifecycle states (Milestone B state machine).

    Lifecycle::
        CREATED -> SUBMITTED -> ACKNOWLEDGED -> {PARTIALLY_FILLED ->}* FILLED
                  |              |
                  v              v
               REJECTED     CANCEL_REQUESTED -> CANCELLED
                             or -> EXPIRED
        any pre-terminal -> FAILED
    """

    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


TERMINAL_STATUSES: frozenset[OrderStatus] = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
        OrderStatus.FAILED,
    }
)


class OrderType(str, Enum):
    """Approved order types — only market orders in this milestone."""

    MARKET = "market"


class FillMode(str, Enum):
    """Deterministic paper-broker fill behaviour (never random)."""

    FULL_FILL = "FULL_FILL"
    PARTIAL_THEN_FILL = "PARTIAL_THEN_FILL"
    REJECT = "REJECT"
    NO_FILL_EXPIRE = "NO_FILL_EXPIRE"


class ExecutionRequestStatus(str, Enum):
    """Intake outcomes persisted on ``ExecutionRequest``.

    ``REJECTED_DUPLICATE`` is not persisted — a duplicate delivery is detected
    via the ``risk_approved_event_id`` unique key and skipped without a new
    row; the value exists here so the status surface is explicit.
    """

    RECEIVED = "RECEIVED"
    ORDER_CREATED = "ORDER_CREATED"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
    REJECTED_INSUFFICIENT_CAPITAL = "REJECTED_INSUFFICIENT_CAPITAL"


@dataclass(frozen=True)
class OrderPlacementRequest:
    """Command value object handed to :meth:`BrokerAdapter.place_order`."""

    order_id: uuid.UUID
    account_id: uuid.UUID
    symbol: str
    side: Side
    order_type: str
    quantity: Decimal
    price: Decimal
    correlation_id: uuid.UUID
    causation_id: uuid.UUID | None = None


@dataclass(frozen=True)
class BrokerAck:
    """Acknowledgment returned by a broker adapter on acceptance."""

    broker_order_ref: str
    message: str = "acknowledged"


@dataclass(frozen=True)
class BrokerCancelResult:
    """Outcome of a cancellation request to a broker adapter."""

    broker_order_ref: str
    cancelled: bool
    message: str = ""


@dataclass(frozen=True)
class BrokerOrderStatus:
    """Read-model snapshot returned by :meth:`BrokerAdapter.get_order_status`."""

    broker_order_ref: str
    status: str  # OPEN / PARTIALLY_FILLED / FILLED / REJECTED / CANCELLED / EXPIRED
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None


@dataclass(frozen=True)
class SimulatedFill:
    """One deterministic fill a paper broker will produce for an order."""

    sequence: int
    quantity: Decimal
    price: Decimal


@dataclass(frozen=True)
class ExecutionIntakeResult:
    """Outcome of ingesting one ``risk_management.RiskApproved`` event."""

    outcome: str  # CREATED / DUPLICATE / REJECTED_INSUFFICIENT_CAPITAL / UNKNOWN_RULE / NO_DEFAULT_ACCOUNT / INVALID_PAYLOAD
    request_id: uuid.UUID | None = None
    order_id: uuid.UUID | None = None
    reason_message: str = field(default="")
