from __future__ import annotations

from apps.execution.domain.exceptions import InvalidOrderTransition
from apps.execution.domain.value_objects import TERMINAL_STATUSES, OrderStatus

# Approved transition table (Milestone B state machine). PARTIALLY_FILLED may
# transition to itself for successive partial fills.
_ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.CREATED: frozenset({OrderStatus.SUBMITTED, OrderStatus.REJECTED, OrderStatus.FAILED}),
    OrderStatus.SUBMITTED: frozenset({OrderStatus.ACKNOWLEDGED, OrderStatus.REJECTED, OrderStatus.FAILED}),
    OrderStatus.ACKNOWLEDGED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCEL_REQUESTED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.FAILED,
        }
    ),
    OrderStatus.PARTIALLY_FILLED: frozenset(
        {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCEL_REQUESTED,
            OrderStatus.EXPIRED,
            OrderStatus.FAILED,
        }
    ),
    OrderStatus.CANCEL_REQUESTED: frozenset(
        {OrderStatus.CANCELLED, OrderStatus.EXPIRED, OrderStatus.FAILED}
    ),
}


class OrderState:
    """Stateless helpers for the order lifecycle state machine."""

    @staticmethod
    def can_transition(current: str | OrderStatus, next_status: str | OrderStatus) -> bool:
        current = OrderStatus(current)
        next_ = OrderStatus(next_status)
        if current is next_:
            return current is OrderStatus.PARTIALLY_FILLED
        return next_ in _ALLOWED_TRANSITIONS.get(current, frozenset())

    @staticmethod
    def transition(current: str | OrderStatus, next_status: str | OrderStatus) -> OrderStatus:
        """Return the validated destination status, raising on illegal moves."""
        current_enum = OrderStatus(current)
        next_enum = OrderStatus(next_status)
        if not OrderState.can_transition(current_enum, next_enum):
            raise InvalidOrderTransition(current_enum.value, next_enum.value)
        return next_enum

    @staticmethod
    def is_terminal(status: str | OrderStatus) -> bool:
        return OrderStatus(status) in TERMINAL_STATUSES
