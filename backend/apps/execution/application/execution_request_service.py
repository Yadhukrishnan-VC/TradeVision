from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.accounts.infrastructure.models import Account
from apps.common.domain.value_objects import IdempotencyKey
from apps.execution.domain.exceptions import (
    ExecutionRequestValidationError,
    UnknownRuleError,
)
from apps.execution.domain.value_objects import (
    ExecutionIntakeResult,
    ExecutionRequestStatus,
    side_for_rule,
)
from apps.execution.infrastructure.repositories import (
    ExecutionRequestRepository,
    OrderRepository,
)
from apps.portfolio.application.capital_service import CapitalService
from core.services import BaseService


class ExecutionRequestService(BaseService):
    """Intake for ``risk_management.RiskApproved`` events (Milestone B).

    Converts an approved risk decision into an ``ExecutionRequest`` (and a
    ``CREATED`` ``Order``) exactly once. Idempotency is enforced by the
    unique ``risk_approved_event_id`` — a redelivered approval is detected
    before insert (``full_clean``) and skipped, so the whole
    recommendation -> approval -> order chain produces at most one order.

    The default ``Account`` (``is_default=True``) resolves the missing
    ``account_id`` on ``RiskApproved``, mirroring the ``account_capital_created``
    convention used by M4.
    """

    def __init__(
        self,
        request_repo: ExecutionRequestRepository | None = None,
        order_repo: OrderRepository | None = None,
        capital_service: CapitalService | None = None,
    ) -> None:
        super().__init__()
        self._requests = request_repo or ExecutionRequestRepository()
        self._orders = order_repo or OrderRepository()
        self._capital = capital_service or CapitalService()

    def intake(
        self,
        *,
        payload: dict,
        correlation_id: uuid.UUID,
        causation_id: uuid.UUID | None,
        risk_approved_event_id: uuid.UUID,
    ) -> ExecutionIntakeResult:
        """Ingest one RiskApproved event; returns a deterministic outcome."""
        try:
            symbol, rule_id, event_type, entry_price, stop_loss, quantity = self._extract(
                payload
            )
        except ExecutionRequestValidationError as exc:
            return ExecutionIntakeResult(outcome="INVALID_PAYLOAD", reason_message=exc.message)
        except (InvalidOperation, TypeError, ValueError) as exc:
            return ExecutionIntakeResult(
                outcome="INVALID_PAYLOAD",
                reason_message=f"Invalid numeric payload: {exc}",
            )

        try:
            side = side_for_rule(rule_id)
        except UnknownRuleError as exc:
            return ExecutionIntakeResult(outcome="UNKNOWN_RULE", reason_message=exc.message)

        account = self._default_account()
        if account is None:
            return ExecutionIntakeResult(
                outcome="NO_DEFAULT_ACCOUNT",
                reason_message="No default Account (is_default=True) available",
            )

        with transaction.atomic():
            request, created = self._requests.create_from_risk_approved(
                risk_approved_event_id=risk_approved_event_id,
                idempotency_key=IdempotencyKey.generate(str(risk_approved_event_id)).value,
                account_id=account.id,
                symbol=symbol,
                side=side.value,
                quantity=quantity,
                entry_price=entry_price,
                stop_loss=stop_loss,
                correlation_id=correlation_id,
                causation_id=causation_id,
                rule_id=rule_id,
                event_type=event_type,
                status=ExecutionRequestStatus.RECEIVED.value,
            )
            if not created:
                return ExecutionIntakeResult(
                    outcome="DUPLICATE",
                    request_id=request.id,
                    reason_message="Duplicate RiskApproved delivery skipped",
                )

            notional = entry_price * quantity
            available = self._available_capital(account.id)
            if available < notional:
                request.status = ExecutionRequestStatus.REJECTED_INSUFFICIENT_CAPITAL.value
                request.reason_message = (
                    f"Available capital {available} < required notional {notional}"
                )
                request.save(update_fields=["status", "reason_message", "updated_at"])
                return ExecutionIntakeResult(
                    outcome="REJECTED_INSUFFICIENT_CAPITAL",
                    request_id=request.id,
                    reason_message=request.reason_message,
                )

            order = self._orders.create_for_request(request)
            request.status = ExecutionRequestStatus.ORDER_CREATED.value
            request.save(update_fields=["status", "updated_at"])
            return ExecutionIntakeResult(
                outcome="CREATED",
                request_id=request.id,
                order_id=order.id,
            )
    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract(payload: dict) -> tuple[str, str, str, Decimal, Decimal, Decimal]:
        """Validate and normalise the RiskApproved payload shape."""
        symbol = str(payload.get("symbol", "")).strip().upper()
        rule_id = str(payload.get("rule_id", "")).strip()
        event_type = str(payload.get("event_type", "")).strip()
        entry_price = Decimal(str(payload.get("entry_price", "")))
        stop_loss = Decimal(str(payload.get("stop_loss", "")))
        quantity = Decimal(str(payload.get("position_size", "")))

        if not symbol:
            raise ExecutionRequestValidationError("Payload missing 'symbol'")
        if not rule_id:
            raise ExecutionRequestValidationError("Payload missing 'rule_id'")
        if entry_price <= 0:
            raise ExecutionRequestValidationError("entry_price must be positive")
        if stop_loss <= 0:
            raise ExecutionRequestValidationError("stop_loss must be positive")
        if quantity <= 0:
            raise ExecutionRequestValidationError("position_size must be positive")
        return symbol, rule_id, event_type, entry_price, stop_loss, quantity

    @staticmethod
    def _default_account() -> Account | None:
        return Account.objects.filter(is_default=True).order_by("created_at", "id").first()

    def _available_capital(self, account_id: uuid.UUID) -> Decimal:
        state = self._capital.get_state(account_id)
        return state.available_capital if state is not None else Decimal("0")
