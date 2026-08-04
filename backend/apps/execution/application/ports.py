from __future__ import annotations

from typing import Protocol, runtime_checkable

from apps.execution.domain.value_objects import (
    BrokerAck,
    BrokerCancelResult,
    BrokerOrderStatus,
    OrderPlacementRequest,
    SimulatedFill,
)


@runtime_checkable
class BrokerAdapter(Protocol):
    """Port implemented by every broker adapter.

    The paper broker implements this protocol plus a deterministic
    :meth:`~PaperBroker.get_fill_plan` simulation surface; a future live
    broker adapter implements only the protocol methods. The execution engine
    never depends on a concrete broker class.
    """

    def place_order(self, order: OrderPlacementRequest) -> BrokerAck:
        """Submit an order; raise ``BrokerRejection`` when rejected."""
        ...

    def cancel_order(self, broker_order_ref: str) -> BrokerCancelResult:
        """Request cancellation of a previously acknowledged order."""
        ...

    def get_order_status(self, broker_order_ref: str) -> BrokerOrderStatus:
        """Return the current broker-side order status."""
        ...


@runtime_checkable
class SimulatedBroker(Protocol):
    """A broker capable of deterministically planning its own fills."""

    def get_fill_plan(self, broker_order_ref: str) -> list[SimulatedFill]:
        """Return the deterministic fill plan for an acknowledged order."""
        ...
