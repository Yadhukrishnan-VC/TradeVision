from __future__ import annotations

from decimal import Decimal

from django.db import models

from core.models import BaseModel

MONEY_DECIMAL_KWARGS = {
    "max_digits": 20,
    "decimal_places": 8,
}

MONEY_QUANT = Decimal("0.00000001")


def quantize_money(value: Decimal) -> Decimal:
    """Round a money value to the 8-decimal-precision field convention."""
    return value.quantize(MONEY_QUANT)


class ExecutionRequest(BaseModel):
    """Intake record for one ``risk_management.RiskApproved`` event.

    ``risk_approved_event_id`` is the actual idempotency key (a redelivered
    approval is detected before insert via ``full_clean`` and skipped); the
    deterministic ``idempotency_key`` is kept for operational lookup.
    """

    idempotency_key = models.CharField(max_length=64, unique=True)
    account_id = models.UUIDField(db_index=True)
    symbol = models.CharField(max_length=50, db_index=True)
    side = models.CharField(max_length=10)  # LONG / SHORT
    quantity = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    entry_price = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    stop_loss = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    correlation_id = models.UUIDField(db_index=True)
    causation_id = models.UUIDField(null=True, blank=True)
    risk_approved_event_id = models.UUIDField(unique=True)
    rule_id = models.CharField(max_length=255, db_index=True)
    event_type = models.CharField(max_length=50, default="")
    status = models.CharField(max_length=40, db_index=True, default="RECEIVED")
    reason_message = models.TextField(default="", blank=True)

    class Meta:
        db_table = "execution_executionrequest"
        verbose_name = "Execution Request"
        verbose_name_plural = "Execution Requests"
        indexes = [
            models.Index(fields=["account_id", "symbol"], name="idx_exec_req_account_symbol"),
        ]

    def __str__(self) -> str:
        return f"ExecutionRequest({self.status}/{self.symbol}/{self.risk_approved_event_id})"


class Order(BaseModel):
    """Write-model for a paper order placed against the execution engine.

    ``order_id`` (the UUID pk) is the ``order_id`` carried on every
    ``orders.*`` event. The OneToOne to ``ExecutionRequest`` is the second
    idempotency layer — one approval produces at most one order.
    """

    execution_request = models.OneToOneField(
        ExecutionRequest,
        on_delete=models.CASCADE,
        related_name="order",
    )
    account_id = models.UUIDField(db_index=True)
    symbol = models.CharField(max_length=50, db_index=True)
    side = models.CharField(max_length=10)  # LONG / SHORT
    order_type = models.CharField(max_length=10, default="market")
    quantity = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    status = models.CharField(max_length=20, db_index=True, default="CREATED")
    filled_quantity = models.DecimalField(default=0, **MONEY_DECIMAL_KWARGS)
    avg_fill_price = models.DecimalField(null=True, blank=True, **MONEY_DECIMAL_KWARGS)
    limit_price = models.DecimalField(null=True, blank=True, **MONEY_DECIMAL_KWARGS)
    broker_order_ref = models.CharField(max_length=64, null=True, blank=True)
    broker_name = models.CharField(max_length=30, default="paper")
    entry_price = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    stop_loss = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    correlation_id = models.UUIDField(db_index=True)
    causation_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "execution_order"
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        indexes = [
            models.Index(fields=["account_id", "status"], name="idx_exec_order_account_status"),
            models.Index(fields=["account_id", "symbol"], name="idx_exec_order_account_symbol"),
        ]

    def __str__(self) -> str:
        return f"Order({self.status}/{self.symbol}/{self.id})"


class Fill(BaseModel):
    """Journal of one deterministic broker fill for an order.

    ``id`` doubles as ``source_fill_id`` for the idempotent
    ``PositionLedgerService.record_fill`` call, and ``(order, sequence)`` is
    unique so re-derived fill plans skip already-applied fills.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="fills",
    )
    sequence = models.IntegerField()
    quantity = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    price = models.DecimalField(**MONEY_DECIMAL_KWARGS)
    occurred_at = models.DateTimeField()

    class Meta:
        db_table = "execution_fill"
        verbose_name = "Fill"
        verbose_name_plural = "Fills"
        constraints = [
            models.UniqueConstraint(
                fields=["order", "sequence"],
                name="uq_execution_fill_order_sequence",
            ),
        ]
        ordering = ["sequence"]

    def __str__(self) -> str:
        return f"Fill({self.order_id}/seq={self.sequence}/{self.quantity})"
