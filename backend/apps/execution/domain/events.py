from __future__ import annotations

from decimal import Decimal


class OrderEventType:
    """Event type strings published by the paper execution engine.

    These reuse the existing, unmodified ``orders.*`` contract consumed by the
    dashboard ``OrderProjectionService``, ``PortfolioSummaryProjectionService``,
    the journal and the audit log. No new event types are introduced.
    """

    PLACED = "orders.OrderPlaced"
    PARTIALLY_FILLED = "orders.OrderPartiallyFilled"
    FILLED = "orders.OrderFilled"
    CANCELLED = "orders.OrderCancelled"
    REJECTED = "orders.OrderRejected"
    EXPIRED = "orders.OrderExpired"


ALL_ORDER_EVENT_TYPES: frozenset[str] = frozenset(
    {
        OrderEventType.PLACED,
        OrderEventType.PARTIALLY_FILLED,
        OrderEventType.FILLED,
        OrderEventType.CANCELLED,
        OrderEventType.REJECTED,
        OrderEventType.EXPIRED,
    }
)


def fmt_decimal(value: Decimal) -> str:
    """Render a Decimal in its natural numeric form (no trailing zeros)."""
    return format(value.normalize(), "f")
