from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class PnLTimeSeriesPoint:
    snapshot_at: datetime
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    cumulative_pnl: Decimal
    drawdown_pct: Decimal


@dataclass(frozen=True)
class PnLSummaryDTO:
    current_total_pnl: Decimal
    current_unrealized_pnl: Decimal
    peak_cumulative_pnl: Decimal
    current_drawdown_pct: Decimal
    time_series: list[PnLTimeSeriesPoint]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DailyPnLPoint:
    trading_date: str
    realized_pnl: Decimal
    total_pnl: Decimal
    cumulative_pnl: Decimal


@dataclass(frozen=True)
class PerformanceDTO:
    period: str
    win_rate: Decimal
    avg_win: Decimal
    avg_loss: Decimal
    profit_factor: Decimal | None
    expectancy: Decimal
    sharpe_like_ratio: Decimal | None
    total_trades: int
    winning_trades: int
    losing_trades: int


@dataclass(frozen=True)
class RiskSummaryDTO:
    total_exposure: Decimal
    largest_position_pct: Decimal
    sector_concentration_pct: Decimal
    leverage_ratio: Decimal
    active_alerts: list[dict[str, Any]]
