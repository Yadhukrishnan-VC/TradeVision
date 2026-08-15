"""MACRO-CONTEXT-1 — shared test fixtures.

In-memory doubles for the application-layer protocols keep the unit tests
database-free; the integration tests build the real services with the real
ORM repository against the PostgreSQL test DB.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from apps.macro_context.domain.entities import ProvenancedObservation


class FakeMacroObservationRepository:
    """In-memory append-only store with the same key semantics as the ORM."""

    def __init__(self, rows: list[ProvenancedObservation] | None = None) -> None:
        self._rows: dict[tuple[str, str, date, datetime], ProvenancedObservation] = {}
        for row in rows or []:
            self._add(row)

    def _add(self, row: ProvenancedObservation) -> None:
        key = (row.provider, row.series_id, row.observed_at, row.published_at)
        self._rows[key] = row

    def upsert_many(self, observations: list[ProvenancedObservation]) -> int:
        inserted = 0
        for row in observations:
            key = (row.provider, row.series_id, row.observed_at, row.published_at)
            if key not in self._rows:
                self._rows[key] = row
                inserted += 1
        return inserted

    def observations_for_series(
        self,
        series_id: str,
        *,
        published_at_lte: datetime | None = None,
        observed_at_lte: date | None = None,
    ) -> list[ProvenancedObservation]:
        rows = [
            row
            for row in self._rows.values()
            if row.series_id == series_id
        ]
        if published_at_lte is not None:
            rows = [r for r in rows if r.published_at <= published_at_lte]
        if observed_at_lte is not None:
            rows = [r for r in rows if r.observed_at <= observed_at_lte]
        return rows

    def latest_published_at(self, series_id: str) -> datetime | None:
        rows = [r for r in self._rows.values() if r.series_id == series_id]
        if not rows:
            return None
        return max(r.published_at for r in rows)

    def count(self) -> int:
        return len(self._rows)


class ExplodingMacroProvider:
    """Raises on any fetch — used to prove failure isolation."""

    provider_name = "exploding"

    def __init__(self, series_to_fail: set[str] | None = None) -> None:
        self._series_to_fail = set(series_to_fail or [])

    def fetch_observations(
        self,
        series_id: str,
        *,
        realtime_start: date,
        realtime_end: date,
    ) -> list[ProvenancedObservation]:
        if series_id in self._series_to_fail:
            raise RuntimeError(f"boom for {series_id}")
        return []

    def health_check(self) -> dict:
        return {"status": "healthy", "provider": self.provider_name}


def make_observation(
    series_id: str,
    observed: str,
    published: str,
    value: str | Decimal | None,
    *,
    provider: str = "fred",
) -> ProvenancedObservation:
    """Build a ``ProvenancedObservation`` from ISO date strings."""
    return ProvenancedObservation(
        provider=provider,
        series_id=series_id,
        observed_at=date.fromisoformat(observed),
        published_at=datetime.combine(
            date.fromisoformat(published),
            datetime.min.time(),
            tzinfo=timezone.utc,
        ),
        value=None if value is None else Decimal(value),
    )


@pytest.fixture
def repository() -> FakeMacroObservationRepository:
    return FakeMacroObservationRepository()
