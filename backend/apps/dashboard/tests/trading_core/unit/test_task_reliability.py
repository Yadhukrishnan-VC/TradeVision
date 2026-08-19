"""WS4 — dashboard Celery task reliability tests.

Asserts the retry/timeout policy on the maintenance tasks and that the
trade-history export task handles failure (job marked ``failed``) and retries
(no duplicate job rows, converges to ``completed``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.dashboard.infrastructure.trading_core.models import ExportJob, TradeRecord
from apps.dashboard.infrastructure.trading_core.repositories import ExportJobRepository
from apps.dashboard.tasks.trading_core_tasks import (
    generate_trade_history_export,
    rebuild_dashboard_home_summary,
    reconcile_holdings,
    reconcile_open_positions,
    reconcile_orders,
    reconcile_positions_snapshot,
)

pytestmark = pytest.mark.django_db

User = get_user_model()

MAINTENANCE_TASKS = [
    reconcile_open_positions,
    reconcile_holdings,
    rebuild_dashboard_home_summary,
    generate_trade_history_export,
    reconcile_positions_snapshot,
    reconcile_orders,
]


class TestRetryPolicy:
    def test_maintenance_tasks_declare_retry_and_timeout_policy(self) -> None:
        for task in MAINTENANCE_TASKS:
            assert task.autoretry_for == (Exception,)
            assert task.max_retries == 3
            assert task.soft_time_limit is not None
            assert task.time_limit is not None


class TestExportTaskReliability:
    def test_export_failure_marks_job_failed_and_retry_converges(self, user) -> None:
        export_id = uuid.uuid4()
        repo = ExportJobRepository()
        repo.create(
            export_id=export_id,
            account_id=user.id,
            status="pending",
            format="csv",
        )
        TradeRecord.objects.create(
            trade_id=uuid.uuid4(),
            account_id=user.id,
            symbol="RELIANCE",
            side="LONG",
            entry_price=Decimal("250.00"),
            exit_price=Decimal("260.00"),
            quantity=Decimal("100"),
            realized_pnl=Decimal("1000.00"),
            realized_pnl_pct=Decimal("4.00"),
            opened_at=datetime.now(timezone.utc),
            closed_at=datetime.now(timezone.utc),
            holding_period_seconds=3600,
        )

        with patch(
            "apps.dashboard.tasks.trading_core_tasks.TradeRecord.objects.filter",
            side_effect=RuntimeError("transient failure"),
        ):
            with pytest.raises(RuntimeError):
                generate_trade_history_export(str(export_id), str(user.id), {}, "csv")

        job = repo.get(export_id)
        assert job.status == "failed"

        generate_trade_history_export(str(export_id), str(user.id), {}, "csv")

        job = repo.get(export_id)
        assert job.status == "completed"
        assert ExportJob.objects.filter(account_id=user.id).count() == 1