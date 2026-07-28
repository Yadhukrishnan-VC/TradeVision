from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class PineMetadata:
    pine_id: str = ""
    pine_version: str = ""
    pine_timestamp: int | None = None


@dataclass(frozen=True)
class TradingViewPayload:
    ticker: str
    exchange: str
    timeframe: str
    close: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume: int | None = None
    timestamp: int | None = None
    pine_metadata: PineMetadata = field(default_factory=PineMetadata)
    indicators: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
