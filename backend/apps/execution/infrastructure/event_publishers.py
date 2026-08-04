from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from apps.eventbus.application.ports import EventBus
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.execution.domain.events import OrderEventType, fmt_decimal


class ExecutionEventPublisher:
    """Publish the ``orders.*`` lifecycle events for the paper execution engine.

    Payload shapes match the *existing, unmodified* consumers exactly
    (dashboard ``OrderProjectionService`` / ``PortfolioSummaryProjectionService``,
    journal, audit log). Every event carries ``account_id`` because
    ``PortfolioSummaryProjectionService`` reads ``event.payload["account_id"]``
    unconditionally for every ``orders.*`` event it consumes.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._bus = event_bus or get_event_bus()

    def publish_order_placed(
        self,
        *,
        order_id: uuid.UUID,
        account_id: uuid.UUID,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Decimal,
        limit_price: Decimal | None,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None = None,
    ) -> DomainEvent:
        payload: dict[str, Any] = {
            "order_id": str(order_id),
            "account_id": str(account_id),
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": fmt_decimal(quantity),
            "limit_price": fmt_decimal(limit_price) if limit_price is not None else None,
        }
        return self._publish(OrderEventType.PLACED, payload, correlation_id, causation_id)

    def publish_order_partially_filled(
        self,
        *,
        order_id: uuid.UUID,
        account_id: uuid.UUID,
        filled_quantity: Decimal,
        avg_fill_price: Decimal,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None = None,
    ) -> DomainEvent:
        payload = {
            "order_id": str(order_id),
            "account_id": str(account_id),
            "filled_quantity": fmt_decimal(filled_quantity),
            "avg_fill_price": fmt_decimal(avg_fill_price),
        }
        return self._publish(
            OrderEventType.PARTIALLY_FILLED, payload, correlation_id, causation_id
        )

    def publish_order_filled(
        self,
        *,
        order_id: uuid.UUID,
        account_id: uuid.UUID,
        filled_quantity: Decimal,
        avg_fill_price: Decimal,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None = None,
    ) -> DomainEvent:
        payload = {
            "order_id": str(order_id),
            "account_id": str(account_id),
            "filled_quantity": fmt_decimal(filled_quantity),
            "avg_fill_price": fmt_decimal(avg_fill_price),
        }
        return self._publish(OrderEventType.FILLED, payload, correlation_id, causation_id)

    def publish_order_cancelled(
        self,
        *,
        order_id: uuid.UUID,
        account_id: uuid.UUID,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None = None,
    ) -> DomainEvent:
        payload = {"order_id": str(order_id), "account_id": str(account_id)}
        return self._publish(OrderEventType.CANCELLED, payload, correlation_id, causation_id)

    def publish_order_rejected(
        self,
        *,
        order_id: uuid.UUID,
        account_id: uuid.UUID,
        reason_code: str,
        reason_message: str,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None = None,
    ) -> DomainEvent:
        payload = {
            "order_id": str(order_id),
            "account_id": str(account_id),
            "reason_code": reason_code,
            "reason_message": reason_message,
        }
        return self._publish(OrderEventType.REJECTED, payload, correlation_id, causation_id)

    def publish_order_expired(
        self,
        *,
        order_id: uuid.UUID,
        account_id: uuid.UUID,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None = None,
    ) -> DomainEvent:
        payload = {"order_id": str(order_id), "account_id": str(account_id)}
        return self._publish(OrderEventType.EXPIRED, payload, correlation_id, causation_id)

    def _publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None,
    ) -> DomainEvent:
        event = DomainEvent.create(
            event_type=event_type,
            payload=payload,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        self._bus.publish(event)
        return event
