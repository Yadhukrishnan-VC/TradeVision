"""MACRO-CONTEXT-1 — point-in-time macro context builder.

``MacroContextBuilder.build(as_of)`` reconstructs the macro state that was
actually KNOWN at ``as_of``:

1. The repository returns only rows whose ``published_at`` (vintage release
   moment) and ``observed_at`` (period) are on or before ``as_of`` — nothing
   from the future leaks in.
2. For each series, the value of the newest period, using the newest vintage
   released by ``as_of``, is selected.

A row with ``value=None`` (FRED ``"."``) is a *known missing* value: it
suppresses the series for any ``as_of`` between its publish and the later
revision that fills it — a stale earlier value must never be served.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from apps.macro_context.application.ports import MacroObservationRepository
from apps.macro_context.domain.entities import MacroContext, ProvenancedObservation
from apps.macro_context.domain.value_objects import SUPPORTED_SERIES, MacroSeries


class MacroContextBuilder:
    """Build point-in-time macro context from a provenance store."""

    def __init__(self, repository: MacroObservationRepository) -> None:
        self._repository = repository

    def build(self, as_of: datetime) -> MacroContext:
        """Return the macro context known at ``as_of`` (UTC, timezone-aware)."""
        as_of = _to_utc(as_of)
        values: dict[str, Any] = {}
        for series in SUPPORTED_SERIES:
            observations = self._repository.observations_for_series(
                series,
                published_at_lte=as_of,
                observed_at_lte=as_of.date(),
            )
            values[series] = self._point_in_time_value(observations)

        non_null = sum(1 for value in values.values() if value is not None)
        return MacroContext(
            as_of=as_of,
            dgs10=values[MacroSeries.DGS10.value],
            fedfunds=values[MacroSeries.FEDFUNDS.value],
            cpiaucsl=values[MacroSeries.CPIAUCSL.value],
            t10y2y=values[MacroSeries.T10Y2Y.value],
            series_count=non_null,
        )

    @staticmethod
    def _point_in_time_value(
        observations: list[ProvenancedObservation],
    ) -> Any | None:
        """Value of the newest period, newest released vintage — or None."""
        if not observations:
            return None
        newest_period = max(obs.observed_at for obs in observations)
        period_rows = [
            obs for obs in observations if obs.observed_at == newest_period
        ]
        newest_vintage = max(obs.published_at for obs in period_rows)
        for obs in period_rows:
            if obs.published_at == newest_vintage:
                return obs.value
        return None


def _to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"as_of must be timezone-aware, got {value!r}")
    return value.astimezone(timezone.utc)


def get_context_builder() -> MacroContextBuilder:
    """Return the builder wired to the ORM provenance store."""
    from apps.macro_context.infrastructure.repositories import (
        MacroObservationRepository,
    )

    return MacroContextBuilder(repository=MacroObservationRepository())
