from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class PnLSnapshot:
    account_id: UUID
    snapshot_at: datetime
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    cumulative_pnl: Decimal = Decimal("0")
    peak_cumulative_pnl: Decimal = Decimal("0")
    drawdown_pct: Decimal = Decimal("0")
    last_event_id: UUID | None = None


@dataclass(frozen=True)
class PnLDailyRollup:
    account_id: UUID
    trading_date: datetime
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    cumulative_pnl: Decimal = Decimal("0")
    peak_cumulative_pnl: Decimal = Decimal("0")
    drawdown_pct: Decimal = Decimal("0")


@dataclass(frozen=True)
class PerformanceSnapshot:
    account_id: UUID
    period: str
    computed_at: datetime
    win_rate: Decimal = Decimal("0")
    avg_win: Decimal = Decimal("0")
    avg_loss: Decimal = Decimal("0")
    profit_factor: Decimal | None = None
    expectancy: Decimal = Decimal("0")
    sharpe_like_ratio: Decimal | None = None
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0


@dataclass(frozen=True)
class RiskMetricSnapshot:
    account_id: UUID
    snapshot_at: datetime
    total_exposure: Decimal = Decimal("0")
    largest_position_pct: Decimal = Decimal("0")
    sector_concentration_pct: Decimal = Decimal("0")
    leverage_ratio: Decimal = Decimal("0")


@dataclass(frozen=True)
class RiskAlertProjection:
    alert_id: UUID
    account_id: UUID
    alert_type: str
    severity: str
    message: str
    raised_at: datetime
    resolved_at: datetime | None = None
    last_event_id: UUID | None = None
