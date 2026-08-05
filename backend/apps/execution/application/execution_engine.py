from __future__ import annotations

import uuid

from django.db import transaction

from apps.execution.application.ports import BrokerAdapter
from apps.execution.domain.entities import OrderState
from apps.execution.domain.exceptions import BrokerRejection
from apps.execution.domain.value_objects import (
    FillMode,
    OrderPlacementRequest,
    OrderStatus,
    SimulatedFill,
)
from apps.execution.infrastructure.brokers.paper_broker import PaperBroker
from apps.execution.infrastructure.event_publishers import ExecutionEventPublisher
from apps.execution.infrastructure.models import Order, quantize_money
from apps.execution.infrastructure.repositories import FillRepository, OrderRepository
from apps.portfolio.application.position_ledger_service import PositionLedgerService
from apps.portfolio.domain.exceptions import InsufficientAvailableCapitalError
from apps.portfolio.domain.value_objects import Side
from core.clock import Clock, get_clock
from core.services import BaseService


class ExecutionEngine(BaseService):
    """Orchestrates one order through the paper broker to the portfolio ledger.

    Flow (Milestone B)::

        CREATED -> SUBMITTED -> place_order ->
            ACKNOWLEDGED (+ orders.OrderPlaced) ->
            {PARTIALLY_FILLED ->}* FILLED (+ orders.OrderPartiallyFilled /
                                             orders.OrderFilled)
        place_order rejection -> REJECTED (+ orders.OrderRejected)
        NO_FILL_EXPIRE -> EXPIRED (+ orders.OrderExpired)
        ledger rejection -> FAILED

    Every fill is applied to ``PositionLedgerService.record_fill`` with
    ``source_fill_id=fill.id`` (idempotent) and the order's correlation ids, so
    the recommendation -> risk -> execution -> portfolio chain stays traceable.

    Idempotency: the engine is keyed on ``order_id`` and re-derives the
    deterministic fill plan; already-applied fills (rows in the ``Fill``
    journal) are skipped and terminal orders are left untouched, so task
    redelivery never double-publishes or double-fills.
    """

    def __init__(
        self,
        broker: BrokerAdapter | None = None,
        order_repo: OrderRepository | None = None,
        fill_repo: FillRepository | None = None,
        ledger: PositionLedgerService | None = None,
        events: ExecutionEventPublisher | None = None,
        clock: Clock | None = None,
    ) -> None:
        super().__init__()
        self._broker = broker or PaperBroker(mode=FillMode.FULL_FILL)
        self._orders = order_repo or OrderRepository()
        self._fills = fill_repo or FillRepository()
        self._ledger = ledger or PositionLedgerService()
        self._events = events or ExecutionEventPublisher()
        self._clock = clock or get_clock()

    def execute_order(self, order_id: uuid.UUID) -> dict[str, str]:
        """Execute (or resume) the order; returns its final status."""
        order = self._orders.get_by_id(order_id)
        if order is None:
            return {"status": "MISSING", "order_id": str(order_id)}
        if OrderState.is_terminal(order.status):
            return {"status": order.status, "order_id": str(order_id)}
        self._execute(order)
        order.refresh_from_db()
        return {"status": order.status, "order_id": str(order_id)}

    # ------------------------------------------------------------------
    # Internal orchestration
    # ------------------------------------------------------------------

    def _execute(self, order: Order) -> None:
        if order.status in (OrderStatus.CREATED.value, OrderStatus.SUBMITTED.value):
            if order.status == OrderStatus.CREATED.value:
                self._transition(order, OrderStatus.SUBMITTED)
            ack = self._place(order)
            if ack is None:
                return
            order.broker_order_ref = ack.broker_order_ref
            self._events.publish_order_placed(
                order_id=order.id,
                account_id=order.account_id,
                symbol=order.symbol,
                side=order.side,
                order_type=order.order_type,
                quantity=order.quantity,
                limit_price=None,
                correlation_id=order.correlation_id,
                causation_id=order.causation_id,
            )
            self._transition(order, OrderStatus.ACKNOWLEDGED)

        plan = self._fill_plan(order)
        if not plan:
            self._transition(order, OrderStatus.EXPIRED)
            self._events.publish_order_expired(
                order_id=order.id,
                account_id=order.account_id,
                correlation_id=order.correlation_id,
                causation_id=order.causation_id,
            )
            return

        final_sequence = plan[-1].sequence
        for planned in plan:
            if self._fills.has_sequence(order_id=order.id, sequence=planned.sequence):
                continue
            self._apply_fill(order, planned, is_final=planned.sequence == final_sequence)

    def _place(self, order: Order) -> object | None:
        """Submit to the broker; ``None`` when the broker rejected it."""
        request = OrderPlacementRequest(
            order_id=order.id,
            account_id=order.account_id,
            symbol=order.symbol,
            side=Side(order.side),
            order_type=order.order_type,
            quantity=order.quantity,
            price=order.entry_price,
            correlation_id=order.correlation_id,
            causation_id=order.causation_id,
        )
        try:
            return self._broker.place_order(request)
        except BrokerRejection as exc:
            self._logger.warning(
                "order_rejected_by_broker",
                extra={
                    "order_id": str(order.id),
                    "reason_code": exc.reason_code,
                    "reason_message": exc.reason_message,
                },
            )
            self._transition(order, OrderStatus.REJECTED)
            self._events.publish_order_rejected(
                order_id=order.id,
                account_id=order.account_id,
                reason_code=exc.reason_code,
                reason_message=exc.reason_message,
                correlation_id=order.correlation_id,
                causation_id=order.causation_id,
            )
            return None

    def _fill_plan(self, order: Order) -> list[SimulatedFill]:
        getter = getattr(self._broker, "get_fill_plan", None)
        if callable(getter):
            return list(getter(order.broker_order_ref) or [])
        # Non-simulated adapter: a single full fill at the reference price.
        return [SimulatedFill(sequence=1, quantity=order.quantity, price=order.entry_price)]

    def _apply_fill(self, order: Order, planned: SimulatedFill, *, is_final: bool) -> None:
        try:
            with transaction.atomic():
                fill = self._fills.create_for_order(
                    order=order,
                    sequence=planned.sequence,
                    quantity=planned.quantity,
                    price=planned.price,
                    occurred_at=self._clock.now(),
                )
                new_filled = order.filled_quantity + planned.quantity
                order.filled_quantity = quantize_money(new_filled)
                order.avg_fill_price = quantize_money(planned.price)
                if is_final:
                    self._transition(order, OrderStatus.FILLED)
                    self._events.publish_order_filled(
                        order_id=order.id,
                        account_id=order.account_id,
                        filled_quantity=order.filled_quantity,
                        avg_fill_price=order.avg_fill_price,
                        correlation_id=order.correlation_id,
                        causation_id=order.causation_id,
                    )
                else:
                    self._transition(order, OrderStatus.PARTIALLY_FILLED)
                    self._events.publish_order_partially_filled(
                        order_id=order.id,
                        account_id=order.account_id,
                        filled_quantity=order.filled_quantity,
                        avg_fill_price=order.avg_fill_price,
                        correlation_id=order.correlation_id,
                        causation_id=order.causation_id,
                    )
                self._ledger.record_fill(
                    account_id=order.account_id,
                    symbol=order.symbol,
                    side=Side(order.side),
                    quantity=planned.quantity,
                    price=planned.price,
                    occurred_at=fill.occurred_at,
                    source_fill_id=fill.id,
                    correlation_id=order.correlation_id,
                    causation_id=order.causation_id,
                )
        except InsufficientAvailableCapitalError:
            self._logger.warning(
                "order_failed_insufficient_capital",
                extra={
                    "order_id": str(order.id),
                    "symbol": order.symbol,
                    "required": str(planned.quantity * planned.price),
                },
            )
            self._transition(order, OrderStatus.FAILED)

    @staticmethod
    def _transition(order: Order, next_status: str) -> None:
        validated = OrderState.transition(order.status, next_status)
        order.status = validated.value
        order.save()
