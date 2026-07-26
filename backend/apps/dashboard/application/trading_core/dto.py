from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class DashboardHomeSummaryDTO:
    account_id: UUID
    open_positions_count: int
    open_orders_count: int
    today_realized_pnl: Decimal
    today_unrealized_pnl: Decimal
    active_alerts_count: int
    broker_connection_status: str
    market_session_status: str
    last_updated_at: datetime | None = None


@dataclass(frozen=True)
class HoldingDTO:
    account_id: UUID
    symbol: str
    quantity: Decimal
    avg_cost: Decimal
    cost_basis: Decimal
    market_value: Decimal | None = None
    allocation_pct: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    opened_at: datetime | None = None


@dataclass(frozen=True)
class PortfolioCompositionDTO:
    account_id: UUID
    holdings: list[HoldingDTO] = field(default_factory=list)
    total_market_value: Decimal = Decimal("0")
    total_cost_basis: Decimal = Decimal("0")
    cash_balance: Decimal = Decimal("0")


@dataclass(frozen=True)
class PositionSnapshotDTO:
    position_id: UUID
    account_id: UUID
    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    unrealized_pnl_pct: Decimal | None = None
    is_open: bool = True
    opened_at: datetime | None = None
    closed_at: datetime | None = None


@dataclass(frozen=True)
class OrderSnapshotDTO:
    order_id: UUID
    account_id: UUID
    symbol: str
    side: str
    order_type: str
    status: str
    quantity: Decimal
    filled_quantity: Decimal
    avg_fill_price: Decimal | None = None
    limit_price: Decimal | None = None
    placed_at: datetime | None = None


@dataclass(frozen=True)
class TradeRecordDTO:
    trade_id: UUID
    account_id: UUID
    symbol: str
    side: str
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    holding_period_seconds: int = 0


@dataclass(frozen=True)
class ExportJobDTO:
    export_id: UUID
    account_id: UUID
    status: str
    format: str
    file_url: str | None = None
    requested_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
