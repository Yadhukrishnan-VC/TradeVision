from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from apps.dashboard.application.analytics_risk.projectors import (
    PerformanceRollupProjector,
    PnLSnapshotProjector,
    RiskMetricProjector,
)
from apps.dashboard.projection.internal_events import DashboardInternalEvent
from apps.eventbus.domain.events import DomainEvent


def make_position_closed_event() -> DomainEvent:
    return DomainEvent.create(
        event_type="positions.PositionClosed",
        payload={
            "account_id": str(uuid4()),
            "symbol": "BTCUSD",
            "side": "LONG",
            "entry_price": "50000",
            "exit_price": "55000",
            "quantity": "1",
            "realized_pnl": "5000",
            "unrealized_pnl": "0",
        },
        correlation_id=uuid4(),
    )


class TestPnLSnapshotProjector:
    def test_name(self) -> None:
        assert PnLSnapshotProjector.name == "pnl_snapshot_projector"


class TestPerformanceRollupProjector:
    def test_name(self) -> None:
        assert PerformanceRollupProjector.name == "performance_rollup_projector"


class TestRiskMetricProjector:
    def test_name(self) -> None:
        assert RiskMetricProjector.name == "risk_metric_projector"
