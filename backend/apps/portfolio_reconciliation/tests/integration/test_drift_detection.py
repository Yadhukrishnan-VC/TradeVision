"""PORTFOLIO-RECONCILE-1 — integration tests for position reconciliation against real PostgreSQL."""

from __future__ import annotations

import uuid

import pytest

from decimal import Decimal
from django.utils import timezone

from apps.accounts.infrastructure.models import Account
from apps.portfolio_reconciliation.application.position_reconciliation_service import (
    get_position_reconciliation_service,
)
from apps.portfolio_reconciliation.domain.value_objects import DriftClassification
from apps.portfolio_reconciliation.infrastructure.models import DriftRecord


pytestmark = pytest.mark.django_db


class TestDriftDetection:
    def test_fresh_position_creates_snapshot(self, db: object, account: Account) -> None:
        from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
        from apps.portfolio.infrastructure.models import Position

        position = Position.objects.create(
            account_id=account.id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("100"),
            avg_entry_price=Decimal("250.50"),
            opened_at=timezone.now(),
        )

        service = get_position_reconciliation_service()
        result = service.reconcile(account.id)

        assert result.total_drift == 1
        assert result.missing_in_read_model == 1
        snap = PositionSnapshot.objects.get(position_id=position.id)
        assert snap.account_id == account.id
        assert snap.symbol == "RELIANCE"
        assert snap.quantity == Decimal("100")
        assert snap.entry_price == Decimal("250.50")

    def test_no_drift_when_mirroring(self, db: object, account: Account) -> None:
        from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
        from apps.portfolio.infrastructure.models import Position

        position = Position.objects.create(
            account_id=account.id, symbol="RELIANCE", side="LONG",
            quantity=Decimal("200"), avg_entry_price=Decimal("300.00"),
            opened_at=timezone.now(),
        )
        PositionSnapshot.objects.create(
            position_id=position.id,
            account_id=account.id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("200"),
            entry_price=Decimal("300.00"),
            is_open=True,
            opened_at=position.opened_at,
        )

        service = get_position_reconciliation_service()
        result = service.reconcile(account.id)

        assert result.total_drift == 0
        assert result.matched == 1
        assert DriftRecord.objects.filter(account_id=account.id).count() == 0

    def test_orphaned_snapshot_never_auto_repaired(self, db: object, account: Account) -> None:
        from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot

        ps = PositionSnapshot.objects.create(
            position_id=uuid.uuid4(),
            account_id=account.id,
            symbol="GHOST",
            side="LONG",
            quantity=Decimal("100"),
            entry_price=Decimal("100.00"),
            is_open=True,
            opened_at=timezone.now(),
        )

        service = get_position_reconciliation_service()
        result = service.reconcile(account.id)

        assert result.orphaned_in_read_model == 1
        drift = DriftRecord.objects.get(account_id=account.id)
        assert drift.classification == DriftClassification.ORPHANED_IN_READ_MODEL
        assert drift.auto_repaired is False

class TestDriftRecordPersistence:
    def test_drift_record_appends_not_updates(self, db: object, account: Account) -> None:
        from apps.portfolio.infrastructure.models import Position

        position = Position.objects.create(
            account_id=account.id, symbol="INFY", side="LONG",
            quantity=Decimal("100"), avg_entry_price=Decimal("100.00"),
            opened_at=timezone.now(),
        )

        service = get_position_reconciliation_service()
        service.reconcile(account.id)
        service.reconcile(account.id)

        assert DriftRecord.objects.filter(account_id=account.id).count() == 1

    def test_drift_record_contains_expected_vs_actual(self, db: object, account: Account) -> None:
        from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
        from apps.portfolio.infrastructure.models import Position

        position = Position.objects.create(
            account_id=account.id, symbol="HDFCBANK", side="LONG",
            quantity=Decimal("100"), avg_entry_price=Decimal("1500.00"),
            opened_at=timezone.now(),
        )
        PositionSnapshot.objects.create(
            position_id=uuid.uuid4(),
            account_id=account.id,
            symbol="HDFCBANK",
            side="LONG",
            quantity=Decimal("50"),
            entry_price=Decimal("1500.00"),
            is_open=True,
            opened_at=position.opened_at,
        )

        service = get_position_reconciliation_service()
        service.reconcile(account.id)

        drift = DriftRecord.objects.get(account_id=account.id)
        assert drift.expected_snapshot is not None
        assert drift.actual_snapshot is not None


class TestRepairVerification:
    def test_stale_position_is_repaired(self, db: object, account: Account) -> None:
        from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
        from apps.portfolio.infrastructure.models import Position

        position = Position.objects.create(
            account_id=account.id, symbol="RELIANCE", side="LONG",
            quantity=Decimal("500"), avg_entry_price=Decimal("2350.25"),
            opened_at=timezone.now(),
        )
        PositionSnapshot.objects.create(
            position_id=uuid.uuid4(),
            account_id=account.id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("100"),
            entry_price=Decimal("2500.00"),
            is_open=True,
            opened_at=position.opened_at,
        )

        service = get_position_reconciliation_service()
        result = service.reconcile(account.id)

        assert result.stale_in_read_model == 1
        snap = PositionSnapshot.objects.get(symbol="RELIANCE")
        assert snap.quantity == Decimal("500")
        assert snap.entry_price == Decimal("2350.25")
        drift = DriftRecord.objects.get(account_id=account.id)
        assert drift.auto_repaired is True
        assert drift.repaired_at is not None


class TestIdempotentNoOp:
    def test_rerun_with_no_drift_is_noop(self, db: object, account: Account) -> None:
        from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
        from apps.portfolio.infrastructure.models import Position

        position = Position.objects.create(
            account_id=account.id, symbol="RELIANCE", side="LONG",
            quantity=Decimal("100"), avg_entry_price=Decimal("250.00"),
            opened_at=timezone.now(),
        )
        PositionSnapshot.objects.create(
            position_id=position.id,
            account_id=account.id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("100"),
            entry_price=Decimal("250.00"),
            is_open=True,
            opened_at=position.opened_at,
        )

        service = get_position_reconciliation_service()
        result = service.reconcile(account.id)

        assert result.total_drift == 0
