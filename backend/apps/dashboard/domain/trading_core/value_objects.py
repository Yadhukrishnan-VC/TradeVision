from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("Money amount cannot be negative")

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("Cannot add Money with different currencies")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("Cannot subtract Money with different currencies")
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, multiplier: Decimal) -> Money:
        return Money(self.amount * multiplier, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)


@dataclass(frozen=True)
class Symbol:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("Symbol must not be empty")
        if len(self.value) > 20:
            raise ValueError("Symbol must not exceed 20 characters")

    def __str__(self) -> str:
        return self.value.upper()


class OrderStatus(enum.Enum):
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TradeSide(enum.Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class BrokerConnectionStatus(enum.Enum):
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


class MarketSessionStatus(enum.Enum):
    PRE_MARKET = "pre_market"
    OPEN = "open"
    CLOSED = "closed"
    POST_MARKET = "post_market"
