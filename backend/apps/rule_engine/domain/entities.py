from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from core.rules.base_rule import RuleSeverity


@dataclass(frozen=True)
class RuleFiring:
    rule_id: str
    event_type: str
    severity: RuleSeverity
    symbol: str
    trigger_data: dict
    analysis_event_id: UUID
    occurred_at: datetime
