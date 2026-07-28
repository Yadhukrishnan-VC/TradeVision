from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class MemoryEntrySnapshot:
    recommendation_id: UUID
    event_type: str
    payload: dict
    occurred_at: datetime


@dataclass(frozen=True)
class MemoryProjectionSnapshot:
    strategy_id: UUID
    sample_size: int
    win_rate: Decimal
    avg_confidence_at_publish: Decimal
    last_recomputed_at: datetime
