"""PORTFOLIO-RECONCILE-1 — Django ORM repositories.

Three repositories implement the application-layer protocols from
``apps.portfolio_reconciliation.application.ports``:

- :class:`PositionSnapshotRepository` / :class:`OrderSnapshotRepository`
  read and (only where the application service classified a row as
  auto-repairable) repair the dashboard read-model tables. The source of
  truth (``apps.portfolio.Position``, ``apps.execution.Order``) is never
  written here — this batch reads it through the existing portfolio /
  execution repositories only.
- :class:`DriftRecordRepository` is the append-only detection log.

Every repair write takes ``select_for_update()`` on the target row,
serialising against a racing projector update exactly as
``apps.pipeline_health``'s heartbeat upsert does. Metadata: a repair sets
``projection_updated_at`` and bumps ``projection_version`` (this row was
brought back into agreement with the write model); ``last_event_id`` /
``last_event_version`` are deliberately NOT touched — a repair has no
source event, and writing a fabricated id would corrupt the projection
metadata contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.dashboard.infrastructure.trading_core.models import (
    OrderSnapshot,
    PositionSnapshot,
)
from apps.portfolio_reconciliation.domain.exceptions import DriftPersistenceError
from apps.portfolio_reconciliation.domain.value_objects import (
    DriftClassification,
)
from apps.portfolio_reconciliation.infrastructure.models import DriftRecord


class PositionSnapshotRepository:
    """Read/write access to the dashboard's position read model."""

    def list_open(self, account_id: uuid.UUID) -> list[Any]:
        """Return the account's ``is_open=True`` ``PositionSnapshot`` rows."""
        return list(
            PositionSnapshot.objects.filter(
                account_id=account_id, is_open=True
            )
        )

    def create_open(
        self,
        *,
        position_id: uuid.UUID,
        account_id: uuid.UUID,
        symbol: str,
        side: str,
        quantity: Decimal,
        entry_price: Decimal,
        opened_at: datetime,
    ) -> None:
        """Project a fresh open snapshot from the write-model row.

        Idempotent via ``get_or_create`` on the ``position_id`` primary
        key: if a live projector won the race and already created the row
        (same ``position_id``, the write-model ``Position.id``), this is a
        no-op rather than an ``IntegrityError``.
        """
        try:
            with transaction.atomic():
                now = timezone.now()
                snapshot, _created = PositionSnapshot.objects.get_or_create(
                    position_id=position_id,
                    account_id=account_id,
                    defaults={
                        "symbol": symbol,
                        "side": side,
                        "quantity": quantity,
                        "entry_price": entry_price,
                        "is_open": True,
                        "opened_at": opened_at,
                        "projection_updated_at": now,
                        "projection_version": 1,
                    },
                )
                if not _created:
                    return
        except Exception as exc:  # defensive boundary — never propagates
            raise DriftPersistenceError(
                f"create_open failed for {account_id}/{symbol}: {exc}"
            ) from exc

    def repair_open(
        self,
        *,
        account_id: uuid.UUID,
        symbol: str,
        side: str,
        quantity: Decimal,
        entry_price: Decimal,
        opened_at: datetime,
    ) -> None:
        """Overwrite the open snapshot for (account, symbol) from the write
        model, row-locking it against a racing projector update.

        Only ``is_open=True`` rows are lockable here — the STALE
        classification only ever arises for an open read-model row.
        """
        try:
            with transaction.atomic():
                snapshot = (
                    PositionSnapshot.objects.select_for_update()
                    .filter(account_id=account_id, symbol=symbol, is_open=True)
                    .first()
                )
                if snapshot is None:
                    raise DriftPersistenceError(
                        f"repair_open: no open snapshot for {account_id}/{symbol}"
                    )
                snapshot.side = side
                snapshot.quantity = quantity
                snapshot.entry_price = entry_price
                snapshot.opened_at = opened_at
                snapshot.is_open = True
                snapshot.projection_updated_at = timezone.now()
                snapshot.projection_version += 1
                snapshot.save(
                    update_fields=[
                        "side",
                        "quantity",
                        "entry_price",
                        "opened_at",
                        "is_open",
                        "projection_updated_at",
                        "projection_version",
                    ]
                )
        except Exception as exc:  # defensive boundary — never propagates
            raise DriftPersistenceError(
                f"repair_open failed for {account_id}/{symbol}: {exc}"
            ) from exc


class OrderSnapshotRepository:
    """Read/write access to the dashboard's order read model."""

    def list_all(self, account_id: uuid.UUID) -> list[Any]:
        """Return every ``OrderSnapshot`` row for the account."""
        return list(OrderSnapshot.objects.filter(account_id=account_id))

    def create(
        self,
        *,
        order_id: uuid.UUID,
        account_id: uuid.UUID,
        symbol: str,
        side: str,
        order_type: str,
        status: str,
        quantity: Decimal,
        filled_quantity: Decimal,
        avg_fill_price: Decimal | None,
        limit_price: Decimal | None,
        placed_at: datetime,
    ) -> None:
        """Project a missing order snapshot from the write-model row.

        Idempotent via ``get_or_create`` on the ``order_id`` primary key
        (the write-model ``Order.id``), same race-safe reasoning as
        ``PositionSnapshotRepository.create_open``.
        """
        try:
            with transaction.atomic():
                now = timezone.now()
                _snapshot, _created = OrderSnapshot.objects.get_or_create(
                    order_id=order_id,
                    account_id=account_id,
                    defaults={
                        "symbol": symbol,
                        "side": side,
                        "order_type": order_type,
                        "status": status,
                        "quantity": quantity,
                        "filled_quantity": filled_quantity,
                        "avg_fill_price": avg_fill_price,
                        "limit_price": limit_price,
                        "placed_at": placed_at,
                        "projection_updated_at": now,
                        "projection_version": 1,
                    },
                )
        except Exception as exc:  # defensive boundary — never propagates
            raise DriftPersistenceError(
                f"order snapshot create failed for {order_id}: {exc}"
            ) from exc

    def repair(
        self,
        *,
        order_id: uuid.UUID,
        status: str,
        filled_quantity: Decimal,
        avg_fill_price: Decimal | None,
    ) -> None:
        """Overwrite the snapshot for ``order_id`` from the write model,
        row-locking it against a racing projector update.
        """
        try:
            with transaction.atomic():
                snapshot = (
                    OrderSnapshot.objects.select_for_update()
                    .filter(order_id=order_id)
                    .first()
                )
                if snapshot is None:
                    raise DriftPersistenceError(
                        f"order snapshot repair: no row for {order_id}"
                    )
                snapshot.status = status
                snapshot.filled_quantity = filled_quantity
                snapshot.avg_fill_price = avg_fill_price
                snapshot.projection_updated_at = timezone.now()
                snapshot.projection_version += 1
                snapshot.save(
                    update_fields=[
                        "status",
                        "filled_quantity",
                        "avg_fill_price",
                        "projection_updated_at",
                        "projection_version",
                    ]
                )
        except Exception as exc:  # defensive boundary — never propagates
            raise DriftPersistenceError(
                f"order snapshot repair failed for {order_id}: {exc}"
            ) from exc


class DriftRecordRepository:
    """Append-only persistence for detected drift.

    ``record`` never updates an existing row — it is a pure insert into
    the detection log, so repeated drift on the same key accumulates
    history (mirroring ``apps.journal``'s append-only convention).
    """

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
        try:
            return DriftRecord.objects.create(
                account_id=account_id,
                entity_type=entity_type,
                entity_key=entity_key,
                classification=classification.value,
                expected_snapshot=expected_snapshot,
                actual_snapshot=actual_snapshot,
                auto_repaired=auto_repaired,
                detected_at=detected_at,
                repaired_at=repaired_at,
            )
        except Exception as exc:  # defensive boundary — never propagates
            raise DriftPersistenceError(
                f"drift record persistence failed for {entity_key}: {exc}"
            ) from exc