from __future__ import annotations

from uuid import UUID

from apps.journal.domain.entities import JournalEntrySnapshot
from apps.journal.domain.exceptions import JournalEntryNotFound
from apps.journal.infrastructure.models import JournalEntry
from apps.journal.infrastructure.repositories import JournalRepository


class JournalQueryService:
    def __init__(self) -> None:
        self._repository = JournalRepository()

    def get_entry(self, correlation_id: UUID) -> JournalEntrySnapshot:
        entry = self._repository.get_by_correlation_id(correlation_id)
        if entry is None:
            raise JournalEntryNotFound(f"Journal entry not found for correlation_id={correlation_id}")
        return self._to_snapshot(entry)

    def get_entries(
        self,
        account_id: UUID,
        finalized: bool | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[JournalEntrySnapshot]:
        qs = JournalEntry.objects.filter(account_id=account_id)
        if finalized is not None:
            qs = qs.filter(finalized=finalized)
        qs = qs.order_by("-created_at")[offset : offset + limit]
        return [self._to_snapshot(e) for e in qs]

    def _to_snapshot(self, entry: JournalEntry) -> JournalEntrySnapshot:
        return JournalEntrySnapshot(
            correlation_id=entry.correlation_id,
            account_id=entry.account_id,
            signal_snapshot=entry.signal_snapshot,
            decision_snapshot=entry.decision_snapshot,
            order_events=list(entry.order_events) if entry.order_events else None,
            position_id=entry.position_id,
            outcome=entry.outcome,
            realized_pnl=entry.realized_pnl,
            finalized=entry.finalized,
            finalized_at=entry.finalized_at,
        )
