from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from apps.dashboard.infrastructure.trading_core.models import OrderSnapshot
from apps.dashboard.projection.base import BaseProjectionService
from apps.dashboard.projection.internal_events import (
    DashboardInternalEvent,
    publish_internal,
)
from apps.eventbus.domain.events import DomainEvent


class OrderProjectionService(BaseProjectionService):
    name = "order_projector"

    def _apply(self, event: DomainEvent) -> None:
        event_type = event.event_type

        if event_type == "orders.OrderPlaced":
            self._apply_placed(event)
        elif event_type == "orders.OrderPartiallyFilled":
            self._apply_partially_filled(event)
        elif event_type == "orders.OrderFilled":
            self._apply_filled(event)
        elif event_type == "orders.OrderCancelled":
            self._apply_cancelled(event)
        elif event_type == "orders.OrderRejected":
            self._apply_rejected(event)
        elif event_type == "orders.OrderExpired":
            self._apply_expired(event)
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "Unhandled event type in OrderProjectionService",
                extra={"event_type": event_type, "event_id": str(event.event_id)},
            )

    def _apply_placed(self, event: DomainEvent) -> None:
        payload = event.payload
        account_id = self._get_account_id(event)

        order = OrderSnapshot(
            order_id=UUID(payload["order_id"]),
            account_id=account_id,
            symbol=payload["symbol"],
            side=payload["side"],
            order_type=payload.get("order_type", "market"),
            status="pending",
            quantity=Decimal(str(payload["quantity"])),
            filled_quantity=Decimal("0"),
            limit_price=Decimal(str(payload["limit_price"])) if payload.get("limit_price") else None,
            placed_at=event.occurred_at,
        )
        self._update_projection_metadata(order, event)
        order.save()

        self._fire_projected_event(order, event)

    def _apply_partially_filled(self, event: DomainEvent) -> None:
        payload = event.payload
        order = self._get_order(payload)
        if order is None:
            return

        order.status = "partially_filled"
        order.filled_quantity = Decimal(str(payload.get("filled_quantity", order.filled_quantity)))
        if payload.get("avg_fill_price"):
            order.avg_fill_price = Decimal(str(payload["avg_fill_price"]))
        self._update_projection_metadata(order, event)
        order.save()

        self._fire_projected_event(order, event)

    def _apply_filled(self, event: DomainEvent) -> None:
        payload = event.payload
        order = self._get_order(payload)
        if order is None:
            return

        order.status = "filled"
        order.filled_quantity = Decimal(str(payload.get("filled_quantity", order.filled_quantity)))
        if payload.get("avg_fill_price"):
            order.avg_fill_price = Decimal(str(payload["avg_fill_price"]))
        self._update_projection_metadata(order, event)
        order.save()

        self._fire_projected_event(order, event)

    def _apply_cancelled(self, event: DomainEvent) -> None:
        payload = event.payload
        order = self._get_order(payload)
        if order is None:
            return

        order.status = "cancelled"
        self._update_projection_metadata(order, event)
        order.save()

        self._fire_projected_event(order, event)

    def _apply_rejected(self, event: DomainEvent) -> None:
        payload = event.payload
        order = self._get_order(payload)
        if order is None:
            return

        order.status = "rejected"
        self._update_projection_metadata(order, event)
        order.save()

        self._fire_projected_event(order, event)

    def _apply_expired(self, event: DomainEvent) -> None:
        payload = event.payload
        order = self._get_order(payload)
        if order is None:
            return

        order.status = "expired"
        self._update_projection_metadata(order, event)
        order.save()

        self._fire_projected_event(order, event)

    def _get_order(self, payload: dict) -> OrderSnapshot | None:
        try:
            return OrderSnapshot.objects.get(order_id=UUID(payload["order_id"]))
        except OrderSnapshot.DoesNotExist:
            return None

    def _fire_projected_event(self, order: OrderSnapshot, event: DomainEvent) -> None:
        internal_event = DashboardInternalEvent.create(
            event_type="order_status_projected",
            payload={
                "account_id": str(order.account_id),
                "order_id": str(order.order_id),
                "status": order.status,
            },
            source_event_id=event.event_id,
        )
        publish_internal(internal_event)
