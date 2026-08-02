from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from apps.portfolio.domain.exceptions import (
    InsufficientAvailableCapitalError,
    InsufficientCashError,
    PortfolioDomainError,
)
from apps.portfolio.domain.value_objects import CapitalAdjustmentReason
from apps.portfolio.infrastructure.event_publishers import PortfolioEventPublisher
from apps.portfolio.infrastructure.models import (
    AccountCapitalState,
    quantize_money,
)
from apps.portfolio.infrastructure.repositories import AccountCapitalRepository
from core.services import BaseService


class CapitalService(BaseService):
    """Authoritative per-account capital ledger (ADR-028 §2.2, §2.3).

    Every mutation validates the invariant it touches, updates the ledger
    field implied by the reason, recomputes the derived fields
    ``available_capital = cash - margin_used`` and
    ``equity = cash + unrealized_pnl_today``, and publishes
    ``portfolio.AccountCapitalChanged``.

    This is the *only* entry point for capital changes — a future broker
    adapter calls these same methods instead of getting a parallel path
    (ADR-028 §2.13, §21).
    """

    def __init__(
        self,
        capital_repo: AccountCapitalRepository | None = None,
        event_publisher: PortfolioEventPublisher | None = None,
    ) -> None:
        super().__init__()
        self._capitals = capital_repo or AccountCapitalRepository()
        self._events = event_publisher or PortfolioEventPublisher()

    # ------------------------------------------------------------------
    # Public ledger operations
    # ------------------------------------------------------------------

    def deposit(
        self,
        account_id: uuid.UUID,
        amount: Decimal,
        *,
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
    ) -> AccountCapitalState:
        """Increase cash by *amount*."""
        self._validate_positive_amount(amount)
        state = self._state(account_id)
        state.cash += amount
        return self._save_adjustment(
            state, reason=CapitalAdjustmentReason.DEPOSIT, correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def withdraw(
        self,
        account_id: uuid.UUID,
        amount: Decimal,
        *,
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
    ) -> AccountCapitalState:
        """Decrease cash by *amount*; reject a withdrawal beyond cash."""
        self._validate_positive_amount(amount)
        state = self._state(account_id)
        if amount > state.cash:
            raise InsufficientCashError(
                f"Withdrawal {amount} exceeds cash {state.cash}",
                code="INSUFFICIENT_CASH",
                details={"cash": str(state.cash), "amount": str(amount)},
            )
        state.cash -= amount
        return self._save_adjustment(
            state, reason=CapitalAdjustmentReason.WITHDRAWAL, correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def reserve_margin(
        self,
        account_id: uuid.UUID,
        amount: Decimal,
        *,
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
    ) -> AccountCapitalState:
        """Reserve *amount* of margin for a new/increased position.

        Rejected when the reserve would exceed available capital
        (``cash - margin_used``) — the ADR-028 §25 invariant.
        """
        self._validate_positive_amount(amount)
        state = self._state(account_id)
        if amount > state.available_capital:
            raise InsufficientAvailableCapitalError(
                f"Reserving {amount} exceeds available capital {state.available_capital}",
                code="INSUFFICIENT_AVAILABLE_CAPITAL",
                details={
                    "available_capital": str(state.available_capital),
                    "amount": str(amount),
                },
            )
        state.margin_used += amount
        return self._save_adjustment(
            state, reason=CapitalAdjustmentReason.MARGIN_RESERVED, correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def release_margin(
        self,
        account_id: uuid.UUID,
        amount: Decimal,
        *,
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
    ) -> AccountCapitalState:
        """Release *amount* of previously reserved margin."""
        self._validate_positive_amount(amount)
        state = self._state(account_id)
        if amount > state.margin_used:
            raise PortfolioDomainError(
                f"Releasing {amount} exceeds reserved margin {state.margin_used}",
                code="MARGIN_RELEASE_OVER_RESERVED",
                details={"margin_used": str(state.margin_used), "amount": str(amount)},
            )
        state.margin_used -= amount
        return self._save_adjustment(
            state, reason=CapitalAdjustmentReason.MARGIN_RELEASED, correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def record_realized_pnl(
        self,
        account_id: uuid.UUID,
        realized: Decimal,
        *,
        correlation_id: uuid.UUID | None = None,
        causation_id: uuid.UUID | None = None,
    ) -> AccountCapitalState:
        """Credit (or debit) realized P&L into cash and the daily tally."""
        state = self._state(account_id)
        state.cash += realized
        state.realized_pnl_today += realized
        return self._save_adjustment(
            state, reason=CapitalAdjustmentReason.REALIZED_PNL, correlation_id=correlation_id,
            causation_id=causation_id,
        )

    # ------------------------------------------------------------------
    # Derived-state maintenance (no event — no approved reason code)
    # ------------------------------------------------------------------

    def reconcile_unrealized(
        self,
        account_id: uuid.UUID,
        unrealized: Decimal,
    ) -> AccountCapitalState:
        """Persist the mark-to-market unrealized P&L and recompute equity.

        Called by :class:`PortfolioQueryService` after recomputing from the
        current-price source. Not published: the ADR-028 §10 event list has no
        reason code for a pure mark-to-market tick.
        """
        state = self._state(account_id)
        state.unrealized_pnl_today = unrealized
        self._recompute_derived(state)
        self._quantize(state)
        state.full_clean()
        state.save()
        return state

    def get_state(self, account_id: uuid.UUID) -> AccountCapitalState | None:
        """Return the account's capital state, or ``None`` when absent."""
        return self._capitals.get_for_account(account_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _state(self, account_id: uuid.UUID) -> AccountCapitalState:
        return self._capitals.get_or_create_for_account(account_id)

    def _save_adjustment(
        self,
        state: AccountCapitalState,
        *,
        reason: CapitalAdjustmentReason,
        correlation_id: uuid.UUID | None,
        causation_id: uuid.UUID | None = None,
    ) -> AccountCapitalState:
        self._recompute_derived(state)
        self._quantize(state)
        state.full_clean()
        state.save()
        self._events.publish_account_capital_changed(
            account_id=state.account_id,
            cash=state.cash,
            margin_used=state.margin_used,
            equity=state.equity,
            available_capital=state.available_capital,
            reason=reason,
            correlation_id=correlation_id or uuid.uuid4(),
            causation_id=causation_id,
        )
        return state

    @staticmethod
    def _recompute_derived(state: AccountCapitalState) -> None:
        state.available_capital = state.cash - state.margin_used
        state.equity = state.cash + state.unrealized_pnl_today

    @staticmethod
    def _quantize(state: AccountCapitalState) -> None:
        """Round every money field to the 8-dp persistence convention."""
        state.cash = quantize_money(state.cash)
        state.margin_used = quantize_money(state.margin_used)
        state.equity = quantize_money(state.equity)
        state.available_capital = quantize_money(state.available_capital)
        state.realized_pnl_today = quantize_money(state.realized_pnl_today)
        state.unrealized_pnl_today = quantize_money(state.unrealized_pnl_today)

    @staticmethod
    def _validate_positive_amount(amount: Decimal) -> None:
        if amount is None or amount <= 0:
            raise PortfolioDomainError(
                f"Amount must be positive, got {amount!r}",
                code="INVALID_AMOUNT",
                details={"amount": str(amount) if amount is not None else None},
            )
