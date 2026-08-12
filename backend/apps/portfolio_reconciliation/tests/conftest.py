"""PORTFOLIO-RECONCILE-1 — shared test fixtures.

Lightweight fakes for the application-layer protocols keep the unit tests
database-free; the integration tests construct the real services with real
repositories (against the PostgreSQL test DB) and a fake event publisher so
no Redis/EventBus is needed.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from apps.accounts.domain.value_objects import Role
from apps.eventbus.domain.events import DomainEvent
from apps.portfolio_reconciliation.application.ports import TransactionManager


# ---------------------------------------------------------------------------
# Fakes for the application-layer protocols
# ---------------------------------------------------------------------------


class FakePositionSource:
    """In-memory ``PositionSourceRepository`` (write-model open positions)."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows: list[Any] = list(rows or [])

    def list_open(self, account_id: uuid.UUID) -> list[Any]:  # noqa: ARG002
        return self.rows


class FakeOrderSource:
    """In-memory ``OrderSourceRepository`` (write-model orders)."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows: list[Any] = list(rows or [])

    def list(self, **filters: Any) -> list[Any]:  # noqa: ARG002
        return self.rows


class FakePositionSnapshots:
    """In-memory ``PositionSnapshotRepository`` that records every call."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows: list[Any] = list(rows or [])
        self.created: list[dict[str, Any]] = []
        self.repaired: list[dict[str, Any]] = []

    def list_open(self, account_id: uuid.UUID) -> list[Any]:  # noqa: ARG002
        return [r for r in self.rows if r.is_open]

    def create_open(self, **kwargs: Any) -> None:
        self.created.append(kwargs)
        snapshot = SimpleNamespace(
            position_id=kwargs["position_id"],
            account_id=kwargs["account_id"],
            symbol=kwargs["symbol"],
            side=kwargs["side"],
            quantity=kwargs["quantity"],
            entry_price=kwargs["entry_price"],
            opened_at=kwargs["opened_at"],
            is_open=True,
        )
        self.rows.append(snapshot)

    def repair_open(self, **kwargs: Any) -> None:
        self.repaired.append(kwargs)
        for i, row in enumerate(self.rows):
            if (
                row.account_id == kwargs["account_id"]
                and row.symbol == kwargs["symbol"]
                and row.is_open
            ):
                self.rows[i] = SimpleNamespace(
                    position_id=row.position_id,
                    account_id=row.account_id,
                    symbol=row.symbol,
                    side=kwargs["side"],
                    quantity=kwargs["quantity"],
                    entry_price=kwargs["entry_price"],
                    opened_at=kwargs["opened_at"],
                    is_open=True,
                )
                break


class FakeOrderSnapshots:
    """In-memory ``OrderSnapshotRepository`` that records every call."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows: list[Any] = list(rows or [])
        self.created: list[dict[str, Any]] = []
        self.repaired: list[dict[str, Any]] = []

    def list_all(self, account_id: uuid.UUID) -> list[Any]:  # noqa: ARG002
        return self.rows

    def create(self, **kwargs: Any) -> None:
        self.created.append(kwargs)
        snapshot = SimpleNamespace(
            order_id=kwargs["order_id"],
            account_id=kwargs["account_id"],
            symbol=kwargs["symbol"],
            side=kwargs["side"],
            order_type=kwargs["order_type"],
            status=kwargs["status"],
            quantity=kwargs["quantity"],
            filled_quantity=kwargs["filled_quantity"],
            avg_fill_price=kwargs["avg_fill_price"],
            limit_price=kwargs["limit_price"],
        )
        self.rows.append(snapshot)

    def repair(self, **kwargs: Any) -> None:
        self.repaired.append(kwargs)
        for i, row in enumerate(self.rows):
            if row.order_id == kwargs["order_id"]:
                self.rows[i] = SimpleNamespace(
                    order_id=row.order_id,
                    account_id=row.account_id,
                    symbol=row.symbol,
                    side=row.side,
                    order_type=row.order_type,
                    status=kwargs["status"],
                    quantity=row.quantity,
                    filled_quantity=kwargs["filled_quantity"],
                    avg_fill_price=kwargs["avg_fill_price"],
                    limit_price=row.limit_price,
                )
                break


class FakeDriftRecords:
    """In-memory ``DriftRecordRepository`` that records every call."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, **kwargs: Any) -> Any:
        self.records.append(kwargs)
        return kwargs


class FakeEventPublisher:
    """In-memory ``EventPublisher`` collecting published events."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


class _NoOpTransactionManager:
    """No-op transaction manager for unit tests without a database."""

    @contextlib.contextmanager
    def atomic(self):
        yield


def make_position(
    *,
    account_id: uuid.UUID,
    symbol: str,
    side: str = "LONG",
    quantity: str = "100",
    avg_entry_price: str = "250.50",
) -> SimpleNamespace:
    """Write-model ``Position``-shaped row (no ORM required)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        account_id=account_id,
        symbol=symbol,
        side=side,
        quantity=Decimal(quantity),
        avg_entry_price=Decimal(avg_entry_price),
        opened_at=datetime(2026, 8, 11, 9, 30, tzinfo=timezone.utc),
    )


def make_snapshot(
    *,
    position_id: uuid.UUID | None = None,
    account_id: uuid.UUID,
    symbol: str,
    side: str = "LONG",
    quantity: str = "100",
    entry_price: str = "250.50",
    is_open: bool = True,
) -> SimpleNamespace:
    """``PositionSnapshot``-shaped row (no ORM required)."""
    return SimpleNamespace(
        position_id=position_id or uuid.uuid4(),
        account_id=account_id,
        symbol=symbol,
        side=side,
        quantity=Decimal(quantity),
        entry_price=Decimal(entry_price),
        is_open=is_open,
        opened_at=datetime(2026, 8, 11, 9, 30, tzinfo=timezone.utc),
    )


def make_order(
    *,
    account_id: uuid.UUID,
    order_id: uuid.UUID | None = None,
    symbol: str = "RELIANCE",
    side: str = "LONG",
    status: str = "FILLED",
    quantity: str = "100",
    filled_quantity: str = "100",
    avg_fill_price: str | None = "250.50",
    limit_price: str | None = None,
) -> SimpleNamespace:
    """Write-model ``Order``-shaped row (no ORM required)."""
    return SimpleNamespace(
        id=order_id or uuid.uuid4(),
        account_id=account_id,
        symbol=symbol,
        side=side,
        order_type="market",
        quantity=Decimal(quantity),
        status=status,
        filled_quantity=Decimal(filled_quantity),
        avg_fill_price=Decimal(avg_fill_price) if avg_fill_price is not None else None,
        limit_price=Decimal(limit_price) if limit_price is not None else None,
        created_at=datetime(2026, 8, 11, 9, 30, tzinfo=timezone.utc),
    )


def make_order_snapshot(
    *,
    account_id: uuid.UUID,
    order_id: uuid.UUID,
    symbol: str = "RELIANCE",
    side: str = "LONG",
    status: str = "filled",
    quantity: str = "100",
    filled_quantity: str = "100",
    avg_fill_price: str | None = "250.50",
    limit_price: str | None = None,
) -> SimpleNamespace:
    """``OrderSnapshot``-shaped row (no ORM required)."""
    return SimpleNamespace(
        order_id=order_id,
        account_id=account_id,
        symbol=symbol,
        side=side,
        order_type="market",
        status=status,
        quantity=Decimal(quantity),
        filled_quantity=Decimal(filled_quantity),
        avg_fill_price=Decimal(avg_fill_price) if avg_fill_price is not None else None,
        limit_price=Decimal(limit_price) if limit_price is not None else None,
    )


@pytest.fixture
def publisher() -> FakeEventPublisher:
    return FakeEventPublisher()


@pytest.fixture
def drift_records() -> FakeDriftRecords:
    return FakeDriftRecords()


@pytest.fixture
def staff_user(db: object) -> object:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        username=f"staff-{uuid.uuid4().hex[:8]}",
        password="StaffPass123!",
        role=Role.STAFF.value,
    )


@pytest.fixture
def owner_user(db: object) -> object:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        username=f"owner-{uuid.uuid4().hex[:8]}",
        password="OwnerPass123!",
        role=Role.OWNER.value,
    )


@pytest.fixture
def viewer_user(db: object) -> object:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_user(
        username=f"viewer-{uuid.uuid4().hex[:8]}",
        password="ViewerPass123!",
        role=Role.VIEWER.value,
    )


@pytest.fixture
def account(db: object, owner_user: object) -> object:
    from apps.accounts.infrastructure.models import Account

    return Account.objects.create(name="Reconcile Test Account", owner=owner_user)