from __future__ import annotations

import enum
from decimal import Decimal
from typing import Any


class Timeframe(enum.Enum):
    RAW = "raw"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class RiskLevel(enum.Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class MetricType(enum.Enum):
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    EXPECTANCY = "expectancy"
    AVG_WIN = "avg_win"
    AVG_LOSS = "avg_loss"
    SHARPE_LIKE_RATIO = "sharpe_like_ratio"


class Period(enum.Enum):
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"
    NINETY_DAYS = "90d"
    YTD = "ytd"
    ALL_TIME = "all_time"


class Granularity(enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


PERIOD_DAYS_MAP: dict[Period, int | None] = {
    Period.SEVEN_DAYS: 7,
    Period.THIRTY_DAYS: 30,
    Period.NINETY_DAYS: 90,
    Period.YTD: None,
    Period.ALL_TIME: None,
}
