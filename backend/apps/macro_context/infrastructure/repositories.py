"""MACRO-CONTEXT-1 — Django ORM repository.

Implements ``MacroObservationRepository`` (the application-layer protocol)
against the append-only ``MacroObservation`` table. The point-in-time
windows (``published_at``/``observed_at``) are enforced in SQL so
``MacroContextBuilder`` receives only rows that were knowable at ``as_of``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime

from apps.macro_context.application.ports import MacroObservationRepository
from apps.macro_context.domain.entities import ProvenancedObservation
from apps.macro_context.infrastructure.models import MacroObservation


class MacroObservationRepository(MacroObservationRepository):  # type: ignore[misc]
    """Persistence for the append-only macro observation store."""

    def upsert_many(
        self, observations: Iterable[ProvenancedObservation]
    ) -> int:
        """Insert new vintage rows, ignoring any that already exist.

        Returns the number of rows actually inserted (rows already present
        from an earlier run are not counted). The inserted count is derived
        from the store delta rather than ``bulk_create``'s return value so
        it is correct regardless of ``ignore_conflicts`` semantics.
        """
        rows = [
            MacroObservation(
                provider=obs.provider,
                series_id=obs.series_id,
                observed_at=obs.observed_at,
                published_at=obs.published_at,
                value=obs.value,
            )
            for obs in observations
        ]
        if not rows:
            return 0
        before = MacroObservation.objects.count()
        MacroObservation.objects.bulk_create(rows, ignore_conflicts=True)
        return MacroObservation.objects.count() - before

    def observations_for_series(
        self,
        series_id: str,
        *,
        published_at_lte: datetime | None = None,
        observed_at_lte: date | None = None,
    ) -> list[ProvenancedObservation]:
        queryset = MacroObservation.objects.filter(series_id=series_id)
        if published_at_lte is not None:
            queryset = queryset.filter(published_at__lte=published_at_lte)
        if observed_at_lte is not None:
            queryset = queryset.filter(observed_at__lte=observed_at_lte)
        rows = queryset.order_by("observed_at", "published_at")
        return [
            ProvenancedObservation(
                provider=row.provider,
                series_id=row.series_id,
                observed_at=row.observed_at,
                published_at=row.published_at,
                value=row.value,
            )
            for row in rows
        ]

    def latest_published_at(self, series_id: str) -> datetime | None:
        row = (
            MacroObservation.objects.filter(series_id=series_id)
            .order_by("-published_at")
            .first()
        )
        if row is None:
            return None
        return row.published_at

    def count(self) -> int:
        return MacroObservation.objects.count()
