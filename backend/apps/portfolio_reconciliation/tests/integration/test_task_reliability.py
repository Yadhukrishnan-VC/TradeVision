"""WS4 — portfolio-reconciliation Celery task reliability tests.

Locks in the "retry does not duplicate financial mutation" invariant for the
reconciliation tasks: a retried pass must converge to the same end state and
must never grow the read model. Also asserts the retry/timeout policy that
the ``@shared_task`` decorators declare.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
from apps.portfolio.infrastructure.models import Position
from apps.portfolio_reconciliation.infrastructure.models import DriftRecord
from apps.portfolio_reconciliation.infrastructure.tasks import (
    reconcile_account_orders,
    reconcile_account_positions,
    reconcile_all_accounts,
)

pytestmark = pytest.mark.django_db


class TestRetryPolicy:
    def test_reconcile_tasks_declare_retry_and_timeout_policy(self) -> None:
        for task in (reconcile_account_positions, reconcile_account_orders):
            assert task.autoretry_for == (Exception,)
            assert task.max_retries == 3
            assert task.soft_time_limit == 180
            assert task.time_limit == 240

    def test_fanout_task_is_plain_dispatch(self) -> None:
        # No auto-retry (a fan-out failing midway must not redispatch the
        # whole batch) and no tight time limit — it only enqueues.
        assert not hasattr(reconcile_all_accounts, "autoretry_for")
        assert reconcile_all_accounts.soft_time_limit is None
        assert reconcile_all_accounts.time_limit is None


class TestIdempotencyAcrossRetries:
    def test_retried_reconcile_converges_and_never_duplicates(self, account) -> None:
        """A retried reconciliation pass converges and never duplicates rows."""
        Position.objects.create(
            account_id=account.id,
            symbol="RELIANCE",
            side="LONG",
            quantity=Decimal("200"),
            avg_entry_price=Decimal("250.00"),
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

        reconcile_account_positions(str(account.id))

        snap = PositionSnapshot.objects.get(symbol="RELIANCE")
        assert snap.quantity == Decimal("200")
        assert PositionSnapshot.objects.filter(account_id=account.id).count() == 1
        first_drift_count = DriftRecord.objects.filter(account_id=account.id).count()
        assert first_drift_count == 1

        reconcile_account_positions(str(account.id))

        snap = PositionSnapshot.objects.get(symbol="RELIANCE")
        assert snap.quantity == Decimal("200")
        assert PositionSnapshot.objects.filter(account_id=account.id).count() == 1
        assert DriftRecord.objects.filter(account_id=account.id).count() == first_drift_count


class TestFanOut:
    def test_reconcile_all_accounts_dispatches_positions_and_orders(
        self, account, owner_user, monkeypatch
    ) -> None:
        from apps.accounts.infrastructure.models import Account

        Account.objects.create(name="Second Account", owner=owner_user)

        dispatched: list[tuple[str, str]] = []

        def record_positions(account_id: str) -> None:
            dispatched.append(("positions", account_id))

        def record_orders(account_id: str) -> None:
            dispatched.append(("orders", account_id))

        monkeypatch.setattr(reconcile_account_positions, "delay", record_positions)
        monkeypatch.setattr(reconcile_account_orders, "delay", record_orders)

        reconcile_all_accounts()

        # Enumerates the whole current account table exactly once per side,
        # robust to pre-existing committed rows in the reused test DB.
        current = {str(a.id) for a in Account.objects.all()}
        dispatched_positions = {aid for kind, aid in dispatched if kind == "positions"}
        dispatched_orders = {aid for kind, aid in dispatched if kind == "orders"}
        assert dispatched_positions == current
        assert dispatched_orders == current