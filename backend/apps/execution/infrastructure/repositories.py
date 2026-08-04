from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.execution.infrastructure.models import (
    ExecutionRequest,
    Fill,
    Order,
    quantize_money,
)
from core.repository import BaseRepository

logger = logging.getLogger(__name__)


class ExecutionRequestRepository(BaseRepository[ExecutionRequest]):
    def get_by_id(self, entity_id: uuid.UUID) -> ExecutionRequest | None:
        try:
            return ExecutionRequest.objects.get(id=entity_id)
        except ExecutionRequest.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[ExecutionRequest]:
        return list(ExecutionRequest.objects.filter(**filters).order_by("-created_at"))

    def create_from_risk_approved(
        self,
        *,
        risk_approved_event_id: uuid.UUID,
        idempotency_key: str,
        account_id: uuid.UUID,
        symbol: str,
        side: str,
        quantity: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None,
        rule_id: str,
        event_type: str,
        status: str,
        reason_message: str = "",
    ) -> tuple[ExecutionRequest, bool]:
        """Persist an intake request, returning ``(request, created)``.

        Duplicate delivery is detected *before* insert via ``full_clean``'s
        unique validation (a plain SELECT), so the surrounding transaction is
        never aborted by the guard. A true race on the INSERT raises
        ``IntegrityError`` which propagates for Celery to retry — the retried
        delivery then lands on the duplicate path.
        """
        request = ExecutionRequest(
            risk_approved_event_id=risk_approved_event_id,
            idempotency_key=idempotency_key,
            account_id=account_id,
            symbol=symbol,
            side=side,
            quantity=quantize_money(quantity),
            entry_price=quantize_money(entry_price),
            stop_loss=quantize_money(stop_loss),
            correlation_id=correlation_id,
            causation_id=causation_id,
            rule_id=rule_id,
            event_type=event_type,
            status=status,
            reason_message=reason_message,
        )
        try:
            request.full_clean()
            request.save()
            return request, True
        except ValidationError as exc:
            if "risk_approved_event_id" in exc.message_dict or "idempotency_key" in exc.message_dict:
                existing = ExecutionRequest.objects.get(
                    risk_approved_event_id=risk_approved_event_id
                )
                logger.warning(
                    "duplicate_execution_request_skipped",
                    extra={"risk_approved_event_id": str(risk_approved_event_id)},
                )
                return existing, False
            raise

    def create(self, entity: ExecutionRequest) -> ExecutionRequest:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: ExecutionRequest) -> ExecutionRequest:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        ExecutionRequest.all_objects.filter(id=entity_id).hard_delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return ExecutionRequest.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return ExecutionRequest.objects.filter(**filters).count()


class OrderRepository(BaseRepository[Order]):
    def get_by_id(self, entity_id: uuid.UUID) -> Order | None:
        try:
            return Order.objects.get(id=entity_id)
        except Order.DoesNotExist:
            return None

    def get_by_execution_request(self, request_id: uuid.UUID) -> Order | None:
        try:
            return Order.objects.get(execution_request_id=request_id)
        except Order.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[Order]:
        return list(Order.objects.filter(**filters).order_by("-created_at"))

    def create_for_request(self, request: ExecutionRequest) -> Order:
        """Create the ``CREATED`` order for an accepted execution request."""
        from apps.execution.domain.value_objects import OrderStatus, OrderType

        order = Order(
            execution_request=request,
            account_id=request.account_id,
            symbol=request.symbol,
            side=request.side,
            order_type=OrderType.MARKET.value,
            quantity=request.quantity,
            entry_price=request.entry_price,
            stop_loss=request.stop_loss,
            status=OrderStatus.CREATED.value,
            broker_name="paper",
            correlation_id=request.correlation_id,
            causation_id=request.causation_id,
        )
        order.full_clean()
        order.save()
        return order

    def create(self, entity: Order) -> Order:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: Order) -> Order:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        Order.all_objects.filter(id=entity_id).hard_delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return Order.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return Order.objects.filter(**filters).count()


class FillRepository(BaseRepository[Fill]):
    def get_by_id(self, entity_id: uuid.UUID) -> Fill | None:
        try:
            return Fill.objects.get(id=entity_id)
        except Fill.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[Fill]:
        return list(Fill.objects.filter(**filters).order_by("sequence"))

    def has_sequence(self, *, order_id: uuid.UUID, sequence: int) -> bool:
        return Fill.objects.filter(order_id=order_id, sequence=sequence).exists()

    def create_for_order(
        self,
        *,
        order: Order,
        sequence: int,
        quantity: Decimal,
        price: Decimal,
    ) -> Fill:
        fill = Fill(
            order=order,
            sequence=sequence,
            quantity=quantize_money(quantity),
            price=quantize_money(price),
            occurred_at=timezone.now(),
        )
        fill.full_clean()
        fill.save()
        return fill

    def create(self, entity: Fill) -> Fill:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: Fill) -> Fill:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        Fill.all_objects.filter(id=entity_id).hard_delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return Fill.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return Fill.objects.filter(**filters).count()
