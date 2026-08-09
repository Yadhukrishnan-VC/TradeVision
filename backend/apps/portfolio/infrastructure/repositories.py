from __future__ import annotations

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.portfolio.domain.value_objects import Side
from apps.portfolio.infrastructure.models import (
    AccountCapitalState,
    Position,
    PositionFillExecution,
    quantize_money,
)
from core.repository import BaseRepository

logger = logging.getLogger(__name__)


class AccountCapitalRepository(BaseRepository[AccountCapitalState]):
    """Persistence for the authoritative per-account capital ledger.

    All money math lives in :class:`CapitalService`; this repository is a
    thin get-or-create + save wrapper (business logic never lives in repos).
    """

    def get_by_id(self, entity_id: uuid.UUID) -> AccountCapitalState | None:
        try:
            return AccountCapitalState.objects.get(id=entity_id)
        except AccountCapitalState.DoesNotExist:
            return None

    def get_for_account(self, account_id: uuid.UUID) -> AccountCapitalState | None:
        try:
            return AccountCapitalState.objects.get(account_id=account_id)
        except AccountCapitalState.DoesNotExist:
            return None

    def get_or_create_for_account(
        self, account_id: uuid.UUID
    ) -> AccountCapitalState:
        """Return the account's capital row, creating a zero-balance one first.

        An ``AccountCapitalState`` is normally created alongside ``Account``
        by the ``account_capital_created`` signal (ADR-028 §19); this method
        is the defensive fallback used by the ledger when no row exists yet.
        """
        state = self.get_for_account(account_id)
        if state is not None:
            return state
        state = AccountCapitalState(account_id=account_id)
        state.full_clean()
        state.save()
        return state

    def list(self, **filters: Any) -> list[AccountCapitalState]:
        return list(AccountCapitalState.objects.filter(**filters))

    def create(self, entity: AccountCapitalState) -> AccountCapitalState:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: AccountCapitalState) -> AccountCapitalState:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        AccountCapitalState.all_objects.filter(id=entity_id).hard_delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return AccountCapitalState.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return AccountCapitalState.objects.filter(**filters).count()


class PositionRepository(BaseRepository[Position]):
    """Persistence for Portfolio's open-position write model.

    A closed position is removed (hard-deleted) so the
    ``(account_id, symbol)`` unique constraint stays the "one row per open
    position" guarantee.
    """

    def get_by_id(self, entity_id: uuid.UUID) -> Position | None:
        try:
            return Position.objects.get(id=entity_id)
        except Position.DoesNotExist:
            return None

    def get_open(self, account_id: uuid.UUID, symbol: str) -> Position | None:
        try:
            return Position.objects.get(account_id=account_id, symbol=symbol)
        except Position.DoesNotExist:
            return None

    def list_open(self, account_id: uuid.UUID) -> list[Position]:
        return list(Position.objects.filter(account_id=account_id))

    def create_open(
        self,
        account_id: uuid.UUID,
        symbol: str,
        side: Side,
        quantity: Decimal,
        avg_entry_price: Decimal,
        opened_at: datetime,
        *,
        stop_loss: Decimal | None = None,
    ) -> Position:
        position = Position(
            account_id=account_id,
            symbol=symbol,
            side=side.value,
            quantity=quantize_money(quantity),
            avg_entry_price=quantize_money(avg_entry_price),
            opened_at=opened_at,
            stop_loss=quantize_money(stop_loss) if stop_loss is not None else None,
        )
        position.full_clean()
        position.save()
        return position

    def update_open(
        self,
        account_id: uuid.UUID,
        symbol: str,
        *,
        quantity: Decimal,
        avg_entry_price: Decimal,
    ) -> Position:
        position = self.get_open(account_id, symbol)
        if position is None:
            raise ValueError(f"No open position for {account_id} / {symbol}")
        position.quantity = quantize_money(quantity)
        position.avg_entry_price = quantize_money(avg_entry_price)
        position.full_clean()
        position.save()
        return position

    def close(self, account_id: uuid.UUID, symbol: str) -> None:
        """Remove the open position row for (account_id, symbol)."""
        Position.all_objects.filter(account_id=account_id, symbol=symbol).hard_delete()

    def list(self, **filters: Any) -> list[Position]:
        return list(Position.objects.filter(**filters))

    def create(self, entity: Position) -> Position:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: Position) -> Position:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        Position.all_objects.filter(id=entity_id).hard_delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return Position.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return Position.objects.filter(**filters).count()


class PositionFillExecutionRepository(BaseRepository[PositionFillExecution]):
    """Idempotency guard for applied fills (ADR-028 §2.11).

    ``create_from_fill`` returns ``None`` on a duplicate ``source_fill_id`` —
    the same ``IntegrityError``/``ValidationError`` → skip pattern used by
    ``RuleExecutionRepository.create_from_firing`` and
    ``RiskDecisionRepository.create_from_decision``.
    """

    def get_by_id(self, entity_id: uuid.UUID) -> PositionFillExecution | None:
        try:
            return PositionFillExecution.objects.get(id=entity_id)
        except PositionFillExecution.DoesNotExist:
            return None

    def get_by_source_fill_id(
        self, source_fill_id: uuid.UUID
    ) -> PositionFillExecution | None:
        try:
            return PositionFillExecution.objects.get(source_fill_id=source_fill_id)
        except PositionFillExecution.DoesNotExist:
            return None

    def create_from_fill(
        self,
        *,
        source_fill_id: uuid.UUID,
        account_id: uuid.UUID,
        symbol: str,
        side: Side,
        quantity: Decimal,
        price: Decimal,
        applied_at: datetime,
    ) -> PositionFillExecution | None:
        try:
            execution = PositionFillExecution(
                source_fill_id=source_fill_id,
                account_id=account_id,
                symbol=symbol,
                side=side.value,
                quantity=quantity,
                price=price,
                applied_at=applied_at,
            )
            execution.full_clean()
            execution.save()
            return execution
        except (IntegrityError, ValidationError):
            logger.warning(
                "duplicate_position_fill",
                extra={
                    "source_fill_id": str(source_fill_id),
                    "account_id": str(account_id),
                    "symbol": symbol,
                },
            )
            return None

    def list(self, **filters: Any) -> list[PositionFillExecution]:
        return list(PositionFillExecution.objects.filter(**filters))

    def create(self, entity: PositionFillExecution) -> PositionFillExecution:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: PositionFillExecution) -> PositionFillExecution:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        PositionFillExecution.all_objects.filter(id=entity_id).hard_delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return PositionFillExecution.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return PositionFillExecution.objects.filter(**filters).count()
