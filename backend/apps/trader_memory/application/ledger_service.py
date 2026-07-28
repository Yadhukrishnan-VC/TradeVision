from __future__ import annotations

from datetime import datetime
from typing import Any

from django.db import IntegrityError

from core.services import BaseService
from apps.eventbus.domain.events import DomainEvent
from apps.trader_memory.domain.exceptions import DuplicateMemoryEntry
from apps.trader_memory.infrastructure.models import MemoryEntry
from apps.trader_memory.infrastructure.repositories import MemoryEntryRepository


class LedgerService(BaseService):
    def __init__(self) -> None:
        super().__init__()
        self._repository = MemoryEntryRepository()

    def append_entry(
        self,
        recommendation_id: str,
        event_type: str,
        payload: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> MemoryEntry:
        from django.utils import timezone

        entry = MemoryEntry(
            recommendation_id=recommendation_id,
            event_type=event_type,
            payload=payload,
            occurred_at=occurred_at or timezone.now(),
        )
        try:
            entry.full_clean()
            entry.save()
        except IntegrityError:
            raise DuplicateMemoryEntry(
                f"Duplicate memory entry for {recommendation_id}/{event_type}"
            )
        return entry

    def handle_recommendation_created(self, event: DomainEvent) -> None:
        payload = event.payload
        self.append_entry(
            recommendation_id=payload["recommendation_id"],
            event_type="recommendations.RecommendationCreated",
            payload=payload,
            occurred_at=event.occurred_at,
        )

    def handle_recommendation_status_changed(self, event: DomainEvent) -> None:
        payload = event.payload
        self.append_entry(
            recommendation_id=payload["recommendation_id"],
            event_type="recommendations.RecommendationStatusChanged",
            payload=payload,
            occurred_at=event.occurred_at,
        )
