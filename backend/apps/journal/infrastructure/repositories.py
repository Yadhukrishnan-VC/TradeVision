from __future__ import annotations

from uuid import UUID

from django.db.models.query import QuerySet

from apps.journal.infrastructure.models import JournalEntry


class JournalRepository:
    def get_by_correlation_id(self, correlation_id: UUID) -> JournalEntry | None:
        try:
            return JournalEntry.objects.get(correlation_id=correlation_id)
        except JournalEntry.DoesNotExist:
            return None

    def get_stale_entries(self) -> QuerySet[JournalEntry]:
        from django.utils import timezone
        from datetime import timedelta

        return JournalEntry.objects.filter(
            finalized=False,
            position_id__isnull=False,
            updated_at__lt=timezone.now() - timedelta(hours=24),
        )
