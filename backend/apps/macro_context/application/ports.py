"""MACRO-CONTEXT-1 — application ports (interfaces).

The application services depend only on these protocols, never on Django
ORM models directly, keeping both the ingestion pipeline and the
point-in-time builder testable with fakes.
"""

from __future__ import annotations

import typing
from datetime import date, datetime
from typing import Any, Protocol

from apps.macro_context.domain.entities import ProvenancedObservation


class MacroDataProvider(Protocol):
    """Fetch macro observations with provenance (vintage) metadata."""

    provider_name: str

    def fetch_observations(
        self,
        series_id: str,
        *,
        realtime_start: date,
        realtime_end: date,
    ) -> list[ProvenancedObservation]:
        """Fetch every vintage of ``series_id`` published in the window.

        ``realtime_start``/``realtime_end`` bound the vintage (revision)
        window, so a far-past start returns the full point-in-time history.
        """
        ...

    def health_check(self) -> dict[str, Any]:
        """Return a provider health report (status, latency)."""
        ...


class MacroObservationRepository(Protocol):
    """Persistence interface for the append-only observation store."""

    def upsert_many(self, observations: typing.Iterable[ProvenancedObservation]) -> int:
        """Append new vintage rows idempotently; return the number inserted."""
        ...

    def observations_for_series(
        self,
        series_id: str,
        *,
        published_at_lte: datetime | None = None,
        observed_at_lte: date | None = None,
    ) -> list[ProvenancedObservation]:
        """Return every observation of ``series_id`` within the windows.

        Both windows are optional; when set, only rows whose
        ``published_at``/``observed_at`` fall on or before the bound are
        returned.
        """
        ...

    def latest_published_at(self, series_id: str) -> datetime | None:
        """Return the newest published_at seen for ``series_id``, or None."""
        ...

    def count(self) -> int:
        """Total rows in the store (for observability)."""
        ...
