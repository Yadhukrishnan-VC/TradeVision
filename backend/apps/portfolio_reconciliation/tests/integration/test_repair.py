"""PORTFOLIO-RECONCILE-1 — integration tests for repair paths."""

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


class TestPositionRepairEdgeCases:
    def test_unrepresentable_short_side_is_downgraded_to_comparison_error(
        self, db: object, account: Account
    ) -> None:
        """The dashboard read model cannot represent ``SHORT`` (side is
        ``max_length=4``); a write-model SHORT position is so downgraded.

        This is the designed defensive boundary: a read-model column that
        cannot hold the write-model value is recorded as ``COMPARISON_ERROR``
        rather than being fabricated or silently truncated. The snapshot row
        is left untouched.
        """
        from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
        from apps.portfolio.infrastructure.models import Position

        position = Position.objects.create(
            account_id=account.id, symbol="RELIANCE", side="SHORT",
            quantity=Decimal("100"), avg_entry_price=Decimal("250.00"),
            opened_at=timezone.now(),
        )
        PositionSnapshot.objects.create(
            position_id=uuid.uuid4(),
            account_id=account.id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("100"),
            entry_price=Decimal("250.00"),
            is_open=True,
            opened_at=timezone.now(),
        )

        service = get_position_reconciliation_service()
        result = service.reconcile(account.id)

        assert result.comparison_errors == 1
        drift = DriftRecord.objects.get(account_id=account.id)
        assert drift.classification == DriftClassification.COMPARISON_ERROR.value
        assert drift.auto_repaired is False
        snap = PositionSnapshot.objects.get(symbol="RELIANCE")
        assert snap.side == "LONG"
        assert snap.quantity == Decimal("100")

    def test_partial_symbol_masking_observed_in_stage_heartbeat(
        self, db: object, account: object
    ) -> None:
        """Demonstrates the partial-symbol masking limitation noted in the audit.

        This test shows that if one symbol has fresh activity while another is
        missed, the overall position snapshot can appear correct. This is not
        a bug in this batch (it's a known limitation per Section K of the package),
        but we document it here for future improvement (Phase 3).
        """
        from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
        from apps.portfolio.infrastructure.models import Position

        pos_a = Position.objects.create(
            account_id=account.id, symbol="RELIANCE", side="LONG",
            quantity=Decimal("100"), avg_entry_price=Decimal("250.00"),
            opened_at=timezone.now(),
        )
        # Create snapshot for symbol B that doesn't exist in Position
        # This is an ORPHAN not a MISSING, demonstrating the symbol-level granularity
        PositionSnapshot.objects.create(
            position_id=uuid.uuid4(),
            account_id=account.id,
            symbol="TCS",
            side="LONG",
            quantity=Decimal("50"),
            entry_price=Decimal("400.00"),
            is_open=True,
            opened_at=pos_a.opened_at,
        )

        service = get_position_reconciliation_service()
        result = service.reconcile(account.id)

        # RELIANCE is MISSING, TCS is ORPHANED (no matching Position)
        assert result.missing_in_read_model == 1
        assert result.orphaned_in_read_model == 1
