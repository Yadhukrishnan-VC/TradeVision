from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class JournalEntrySnapshot:
    correlation_id: UUID
    account_id: UUID
    signal_snapshot: dict | None = None
    decision_snapshot: dict | None = None
    order_events: list[dict] | None = None
    position_id: UUID | None = None
    outcome: str | None = None
    realized_pnl: Decimal | None = None
    finalized: bool = False
    finalized_at: datetime | None = None
