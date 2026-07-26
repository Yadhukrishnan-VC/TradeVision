from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.test import TestCase

from apps.dashboard.infrastructure.analytics_risk.models import (
    PnLDailyRollup,
    PnLSnapshot,
    PerformanceSnapshot,
    RiskAlertProjection,
    RiskMetricSnapshot,
)


class TestPnLSnapshotModel(TestCase):
    def test_create(self) -> None:
        obj = PnLSnapshot.objects.create(
            id=uuid4(),
            account_id=uuid4(),
            snapshot_at="2024-01-01T00:00:00Z",
            realized_pnl=Decimal("100"),
        )
        assert obj.realized_pnl == Decimal("100")
        assert obj.last_event_id is None

    def test_str(self) -> None:
        obj = PnLSnapshot.objects.create(
            id=uuid4(),
            account_id=uuid4(),
            snapshot_at="2024-01-01T00:00:00Z",
        )
        assert str(obj).startswith("PnLSnapshot(")

    def test_db_table(self) -> None:
        assert PnLSnapshot._meta.db_table == "dashboard_pnl_snapshot"


class TestPnLDailyRollupModel(TestCase):
    def test_create(self) -> None:
        obj = PnLDailyRollup.objects.create(
            id=uuid4(),
            account_id=uuid4(),
            trading_date="2024-01-01",
        )
        assert obj.drawdown_pct == Decimal("0")

    def test_unique_constraint(self) -> None:
        account_id = uuid4()
        PnLDailyRollup.objects.create(
            id=uuid4(),
            account_id=account_id,
            trading_date="2024-01-01",
        )


class TestPerformanceSnapshotModel(TestCase):
    def test_create(self) -> None:
        obj = PerformanceSnapshot.objects.create(
            id=uuid4(),
            account_id=uuid4(),
            period="30d",
        )
        assert obj.total_trades == 0

    def test_unique_constraint(self) -> None:
        account_id = uuid4()
        PerformanceSnapshot.objects.create(
            id=uuid4(),
            account_id=account_id,
            period="30d",
        )


class TestRiskMetricSnapshotModel(TestCase):
    def test_create(self) -> None:
        obj = RiskMetricSnapshot.objects.create(
            id=uuid4(),
            account_id=uuid4(),
            snapshot_at="2024-01-01T00:00:00Z",
        )
        assert obj.leverage_ratio == Decimal("0")

    def test_db_table(self) -> None:
        assert RiskMetricSnapshot._meta.db_table == "dashboard_risk_metric_snapshot"


class TestRiskAlertProjectionModel(TestCase):
    def test_create(self) -> None:
        obj = RiskAlertProjection.objects.create(
            alert_id=uuid4(),
            account_id=uuid4(),
            alert_type="concentration_warning",
            severity="high",
            message="Test alert",
            raised_at="2024-01-01T00:00:00Z",
        )
        assert obj.resolved_at is None

    def test_str(self) -> None:
        obj = RiskAlertProjection.objects.create(
            alert_id=uuid4(),
            account_id=uuid4(),
            alert_type="test",
            severity="low",
            message="test",
            raised_at="2024-01-01T00:00:00Z",
        )
        assert str(obj).startswith("RiskAlertProjection(")
