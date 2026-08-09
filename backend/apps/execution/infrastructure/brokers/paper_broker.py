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
        commission_rate: Decimal | None = None,
        slippage_bps: Decimal | None = None,
    ) -> None:
        self._mode = FillMode(mode)
        self._fill_price = fill_price
        self._commission_rate = commission_rate
        self._slippage_bps = slippage_bps
        self._book: dict[str, dict] = {}

    def place_order(self, order: OrderPlacementRequest) -> BrokerAck:
        if self._mode is FillMode.REJECT:
            raise BrokerRejection(
                reason_code="BROKER_REJECTED",
                reason_message="Paper broker configured to reject all orders (REJECT mode)",
            )
        ref = str(uuid.uuid4())
        plan = self._build_fill_plan(order)
        fill_price = plan[0].price if plan else (self._fill_price if self._fill_price is not None else order.price)
        self._book[ref] = {
            "order_id": order.order_id,
            "fill_price": fill_price,
            "plan": plan,
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
        from core.execution_context import (
            get_backtest_commission_rate,
            get_backtest_slippage_bps,
            get_next_bar_open,
        )

        ctx_open = get_next_bar_open()
        base_price = (
            ctx_open
            if ctx_open is not None
            else (self._fill_price if self._fill_price is not None else order.price)
        )
        qty = order.quantity

        ctx_comm = get_backtest_commission_rate()
        comm_rate = (
            self._commission_rate
            if self._commission_rate is not None
            else (
                ctx_comm
                if ctx_comm is not None
                else getattr(order, "commission_rate", Decimal("0"))
            )
        )
        ctx_slip = get_backtest_slippage_bps()
        slip_bps = (
            self._slippage_bps
            if self._slippage_bps is not None
            else (
                ctx_slip
                if ctx_slip is not None
                else getattr(order, "slippage_bps", Decimal("0"))
            )
        )

        from apps.portfolio.domain.value_objects import Side
        side_val = getattr(order, "side", Side.LONG)
        side_str = side_val.value if isinstance(side_val, Side) else str(side_val).upper()

        if slip_bps and slip_bps > 0:
            multiplier = Decimal(slip_bps) / Decimal("10000")
            if side_str == "LONG":
                fill_price = base_price * (Decimal("1") + multiplier)
            else:
                fill_price = base_price * (Decimal("1") - multiplier)
        else:
            fill_price = base_price

        slippage_impact = abs(fill_price - base_price) * qty
        commission_fee = (
            qty * fill_price * Decimal(comm_rate) if comm_rate else Decimal("0")
        )

        if self._mode is FillMode.FULL_FILL:
            return [
                SimulatedFill(
                    sequence=1,
                    quantity=qty,
                    price=fill_price,
                    commission_fee=commission_fee,
                    slippage_impact=slippage_impact,
                )
            ]

        if self._mode is FillMode.PARTIAL_THEN_FILL:
            first = (qty * Decimal("60")) / Decimal("100")
            second = qty - first
            fee1 = (
                first * fill_price * Decimal(comm_rate)
                if comm_rate
                else Decimal("0")
            )
            fee2 = (
                second * fill_price * Decimal(comm_rate)
                if comm_rate
                else Decimal("0")
            )
            slip1 = abs(fill_price - base_price) * first
            slip2 = abs(fill_price - base_price) * second
            return [
                SimulatedFill(
                    sequence=1,
                    quantity=first,
                    price=fill_price,
                    commission_fee=fee1,
                    slippage_impact=slip1,
                ),
                SimulatedFill(
                    sequence=2,
                    quantity=second,
                    price=fill_price,
                    commission_fee=fee2,
                    slippage_impact=slip2,
                ),
            ]

        if self._mode is FillMode.NO_FILL_EXPIRE:
            return []

        # REJECT is handled in place_order; anything else is unreachable.
        raise BrokerRejection(
            reason_code="UNSUPPORTED_FILL_MODE",
            reason_message=f"Unsupported fill mode {self._mode.value}",
        )
