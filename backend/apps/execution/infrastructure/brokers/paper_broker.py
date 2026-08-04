from __future__ import annotations

import uuid
from decimal import Decimal

from apps.execution.application.ports import BrokerAdapter
from apps.execution.domain.exceptions import BrokerRejection
from apps.execution.domain.value_objects import (
    BrokerAck,
    BrokerCancelResult,
    BrokerOrderStatus,
    FillMode,
    OrderPlacementRequest,
    SimulatedFill,
)


class PaperBroker(BrokerAdapter):
    """Deterministic, broker-independent paper broker (Milestone B).

    - **No network I/O and no real broker contact.** The paper broker is a
      pure in-memory book; it never imports or reaches Zerodha/Kite or any
      HTTP client.
    - **Explicit, deterministic fills.** Behaviour is chosen by the caller via
      :class:`FillMode` at construction; there is no randomness and no
      wall-clock dependence, so every execution is fully reproducible.
    """

    def __init__(
        self,
        mode: FillMode = FillMode.FULL_FILL,
        *,
        fill_price: Decimal | None = None,
    ) -> None:
        self._mode = FillMode(mode)
        self._fill_price = fill_price
        self._book: dict[str, dict] = {}

    def place_order(self, order: OrderPlacementRequest) -> BrokerAck:
        if self._mode is FillMode.REJECT:
            raise BrokerRejection(
                reason_code="BROKER_REJECTED",
                reason_message="Paper broker configured to reject all orders (REJECT mode)",
            )
        ref = str(uuid.uuid4())
        self._book[ref] = {
            "order_id": order.order_id,
            "fill_price": self._fill_price if self._fill_price is not None else order.price,
            "plan": self._build_fill_plan(order),
            "status": "ACKNOWLEDGED",
        }
        return BrokerAck(broker_order_ref=ref, message="acknowledged")

    def get_fill_plan(self, broker_order_ref: str) -> list[SimulatedFill]:
        """Return the deterministic fill plan for an acknowledged order."""
        entry = self._book.get(broker_order_ref)
        return list(entry["plan"]) if entry else []

    def cancel_order(self, broker_order_ref: str) -> BrokerCancelResult:
        entry = self._book.get(broker_order_ref)
        if entry is None:
            return BrokerCancelResult(
                broker_order_ref=broker_order_ref, cancelled=False, message="unknown order"
            )
        if entry["status"] != "ACKNOWLEDGED":
            return BrokerCancelResult(
                broker_order_ref=broker_order_ref,
                cancelled=False,
                message=f"cannot cancel in status {entry['status']}",
            )
        entry["status"] = "CANCELLED"
        return BrokerCancelResult(
            broker_order_ref=broker_order_ref, cancelled=True, message="cancelled"
        )

    def get_order_status(self, broker_order_ref: str) -> BrokerOrderStatus:
        entry = self._book.get(broker_order_ref)
        if entry is None:
            return BrokerOrderStatus(broker_order_ref=broker_order_ref, status="UNKNOWN")
        plan = entry["plan"]
        total = sum((f.quantity for f in plan), Decimal("0"))
        return BrokerOrderStatus(
            broker_order_ref=broker_order_ref,
            status=entry["status"],
            filled_quantity=total,
            avg_fill_price=entry["fill_price"] if total else None,
        )

    # ------------------------------------------------------------------
    # Deterministic fill planning
    # ------------------------------------------------------------------

    def _build_fill_plan(self, order: OrderPlacementRequest) -> list[SimulatedFill]:
        price = self._fill_price if self._fill_price is not None else order.price
        qty = order.quantity

        if self._mode is FillMode.FULL_FILL:
            return [SimulatedFill(sequence=1, quantity=qty, price=price)]

        if self._mode is FillMode.PARTIAL_THEN_FILL:
            first = (qty * Decimal("60")) / Decimal("100")
            second = qty - first
            return [
                SimulatedFill(sequence=1, quantity=first, price=price),
                SimulatedFill(sequence=2, quantity=second, price=price),
            ]

        if self._mode is FillMode.NO_FILL_EXPIRE:
            return []

        # REJECT is handled in place_order; anything else is unreachable.
        raise BrokerRejection(
            reason_code="UNSUPPORTED_FILL_MODE",
            reason_message=f"Unsupported fill mode {self._mode.value}",
        )
