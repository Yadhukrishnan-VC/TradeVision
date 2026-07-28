from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from apps.technical_analysis.domain.value_objects import PineMetadata


@dataclass(frozen=True)
class TASnapshot:
    symbol: str
    exchange: str
    timeframe: str
    indicators: dict[str, Any]
    pine_metadata: PineMetadata
    raw_payload: dict[str, Any]
    snapshot_timestamp: datetime
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
