from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from apps.dashboard.domain.analytics_risk.entities import (
    PerformanceSnapshot,
    PnLDailyRollup,
    PnLSnapshot,
    RiskAlertProjection,
    RiskMetricSnapshot,
)


class TestEntities:
    def test_pnl_snapshot_defaults(self) -> None:
        snap = PnLSnapshot(
            account_id=uuid4(),
            snapshot_at=datetime(2024, 1, 1),
        )
        assert snap.realized_pnl == Decimal("0")
        assert snap.unrealized_pnl == Decimal("0")
        assert snap.total_pnl == Decimal("0")
        assert snap.last_event_id is None

    def test_pnl_snapshot_with_values(self) -> None:
        snap = PnLSnapshot(
            account_id=uuid4(),
            snapshot_at=datetime(2024, 1, 1),
            realized_pnl=Decimal("100"),
            unrealized_pnl=Decimal("50"),
            total_pnl=Decimal("150"),
        )
        assert snap.total_pnl == Decimal("150")

    def test_daily_rollup_defaults(self) -> None:
        rollup = PnLDailyRollup(
            account_id=uuid4(),
            trading_date=datetime(2024, 1, 1),
        )
        assert rollup.realized_pnl == Decimal("0")

    def test_performance_snapshot(self) -> None:
        snap = PerformanceSnapshot(
            account_id=uuid4(),
            period="30d",
            computed_at=datetime(2024, 1, 1),
            win_rate=Decimal("0.6"),
            total_trades=10,
            winning_trades=6,
            losing_trades=4,
        )
        assert snap.win_rate == Decimal("0.6")
        assert snap.total_trades == 10

    def test_risk_metric_snapshot(self) -> None:
        snap = RiskMetricSnapshot(
            account_id=uuid4(),
            snapshot_at=datetime(2024, 1, 1),
            total_exposure=Decimal("5000"),
        )
        assert snap.total_exposure == Decimal("5000")

    def test_risk_alert_projection(self) -> None:
        alert = RiskAlertProjection(
            alert_id=uuid4(),
            account_id=uuid4(),
            alert_type="concentration_warning",
            severity="high",
            message="Sector concentration > 40%",
            raised_at=datetime(2024, 1, 1),
        )
        assert alert.resolved_at is None
