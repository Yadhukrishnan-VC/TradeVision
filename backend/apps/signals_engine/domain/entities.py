from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from apps.signals_engine.domain.value_objects import SignalDirection


@dataclass(frozen=True)
class Signal:
    id: uuid.UUID
    account_id: uuid.UUID | None
    symbol: str
    timeframe: str
    direction: SignalDirection
    confidence_hint: float
    indicator_snapshot: dict[str, Any]
    source_alert_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
