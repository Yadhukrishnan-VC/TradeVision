"""PORTFOLIO-RECONCILE-1 — application ports (interfaces).

The reconciliation services depend only on these protocols, never on Django
ORM models directly. That keeps the classification logic unit-testable with
lightweight fakes while production wiring passes the real repositories in
(see ``infrastructure/repositories.py`` and the task module).

The *source* protocols are deliberately thin wrappers over the existing,
unmodified portfolio/execution repositories — this batch only ever reads
the write model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol

from apps.eventbus.domain.events import DomainEvent
from apps.portfolio_reconciliation.domain.value_objects import (
    DriftClassification,
)


class PositionSourceRepository(Protocol):
    """Read-only access to the portfolio write model's open positions."""

    def list_open(self, account_id: uuid.UUID) -> list[Any]:
        """Return every open ``apps.portfolio.Position`` row for the account."""
        ...


class OrderSourceRepository(Protocol):
    """Read-only access to the execution write model's orders."""

    def list(self, **filters: Any) -> list[Any]:
        """Return ``apps.execution.Order`` rows filtered by kwargs."""
        ...


class PositionSnapshotRepository(Protocol):
    """Read/write access to the dashboard position read model."""

    def list_open(self, account_id: uuid.UUID) -> list[Any]:
        """Return the account's ``is_open=True`` ``PositionSnapshot`` rows."""
        ...

    def create_open(
        self,
        *,
        position_id: uuid.UUID,
        account_id: uuid.UUID,
        symbol: str,
        side: str,
        quantity: Any,
        entry_price: Any,
        opened_at: datetime,
    ) -> None:
        """Project a fresh open snapshot from the write-model row."""
        ...

    def repair_open(
        self,
        *,
        account_id: uuid.UUID,
        symbol: str,
        side: str,
        quantity: Any,
        entry_price: Any,
        opened_at: datetime,
    ) -> None:
        """Overwrite the open snapshot for (account, symbol) from the write
        model, row-locking it against a racing projector update."""
        ...


class OrderSnapshotRepository(Protocol):
    """Read/write access to the dashboard order read model."""

    def list_all(self, account_id: uuid.UUID) -> list[Any]:
        """Return every ``OrderSnapshot`` row for the account."""
        ...

    def create(
        self,
        *,
        order_id: uuid.UUID,
        account_id: uuid.UUID,
        symbol: str,
        side: str,
        order_type: str,
        status: str,
        quantity: Any,
        filled_quantity: Any,
        avg_fill_price: Any,
        limit_price: Any,
        placed_at: datetime,
    ) -> None:
        """Project a missing order snapshot from the write-model row."""
        ...

    def repair(
        self,
        *,
        order_id: uuid.UUID,
        status: str,
        filled_quantity: Any,
        avg_fill_price: Any,
    ) -> None:
        """Overwrite the snapshot for ``order_id`` from the write model,
        row-locking it against a racing projector update."""
        ...


class DriftRecordRepository(Protocol):
    """Append-only persistence for detected drift."""

    def record(
        self,
        *,
        account_id: uuid.UUID,
        entity_type: str,
        entity_key: str,
        classification: DriftClassification,
        expected_snapshot: dict[str, Any],
        actual_snapshot: dict[str, Any],
        auto_repaired: bool,
        detected_at: datetime,
        repaired_at: datetime | None = None,
    ) -> Any:
        """Persist one drift record and return it.

        Raises:
            DriftPersistenceError: When the row cannot be stored.
        """
        ...


class EventPublisher(Protocol):
    """Publish a domain event out of the reconciliation context."""

    def publish(self, event: DomainEvent) -> None:
        """Publish the given event to the configured EventBus."""
        ...


class TransactionManager(Protocol):
    """Transaction boundary for a reconciliation repair + drift record.

    Production uses Django's ``transaction.atomic()``; unit tests use a no-op
    context manager that yields without a database.
    """

    def atomic(self):
        """Return a context manager for an atomic block."""
        ...
