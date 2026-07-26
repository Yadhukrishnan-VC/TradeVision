from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from apps.dashboard.domain.trading_core.value_objects import (
    BrokerConnectionStatus,
    MarketSessionStatus,
    Money,
    OrderStatus,
    OrderType,
    Symbol,
    TradeSide,
)


@dataclass(frozen=True)
class PositionSnapshot:
    position_id: UUID
    account_id: UUID
    symbol: Symbol
    side: TradeSide
    quantity: Decimal
    entry_price: Decimal
    is_open: bool = True
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: datetime | None = None
    projection_version: int = 0
    projection_updated_at: datetime | None = None
    last_event_id: UUID | None = None
    last_event_version: int = 0


@dataclass(frozen=True)
class OrderSnapshot:
    order_id: UUID
    account_id: UUID
    symbol: Symbol
    side: TradeSide
    order_type: OrderType
    status: OrderStatus
    quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    limit_price: Decimal | None = None
    placed_at: datetime = field(default_factory=datetime.utcnow)
    projection_version: int = 0
    projection_updated_at: datetime | None = None
    last_event_id: UUID | None = None
    last_event_version: int = 0


@dataclass(frozen=True)
class TradeRecord:
    trade_id: UUID
    account_id: UUID
    symbol: Symbol
    side: TradeSide
    entry_price: Decimal
    exit_price: Decimal
    quantity: Decimal
    realized_pnl: Decimal
    realized_pnl_pct: Decimal
    opened_at: datetime
    closed_at: datetime
    holding_period_seconds: int
    projection_version: int = 0
    projection_updated_at: datetime | None = None
    last_event_id: UUID | None = None
    last_event_version: int = 0


@dataclass(frozen=True)
class Holding:
    account_id: UUID
    symbol: Symbol
    quantity: Decimal
    avg_cost: Decimal
    cost_basis: Decimal
    opened_at: datetime = field(default_factory=datetime.utcnow)
    projection_version: int = 0
    projection_updated_at: datetime | None = None
    last_event_id: UUID | None = None
    last_event_version: int = 0


@dataclass(frozen=True)
class PortfolioComposition:
    account_id: UUID
    holdings: list[Holding]
    total_market_value: Money
    total_cost_basis: Money
    cash_balance: Money


@dataclass(frozen=True)
class DashboardHomeAggregate:
    account_id: UUID
    open_positions_count: int = 0
    open_orders_count: int = 0
    today_realized_pnl: Decimal = Decimal("0")
    today_unrealized_pnl: Decimal = Decimal("0")
    active_alerts_count: int = 0
    broker_connection_status: BrokerConnectionStatus = BrokerConnectionStatus.DISCONNECTED
    market_session_status: MarketSessionStatus = MarketSessionStatus.CLOSED
    last_updated_at: datetime | None = None
