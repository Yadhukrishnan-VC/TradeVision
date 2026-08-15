"""MACRO-CONTEXT-1 — deterministic fake macro provider.

Mirrors ``FredMacroProvider``'s contract with a small, fixed vintage matrix
so tests (and local development without a FRED key) can exercise
multi-vintage point-in-time behaviour deterministically. The dataset is a
reduced, synthetic stand-in for real FRED data — never used in production.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from apps.macro_context.domain.entities import ProvenancedObservation

_MISSING = None


class FakeMacroProvider:
    """Deterministic provider returning canned vintage rows per series."""

    provider_name = "fake"

    def fetch_observations(
        self,
        series_id: str,
        *,
        realtime_start: date,
        realtime_end: date,
    ) -> list[ProvenancedObservation]:
        rows = _CANNED.get(series_id, [])
        result = [
            row
            for row in rows
            if realtime_start <= row.published_at.date() <= realtime_end
        ]
        return list(result)

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "provider": self.provider_name,
            "latency_ms": 0.0,
            "note": "Fake provider — canned vintages.",
        }


def _obs(series: str, observed: str, published: str, value: Decimal | None) -> ProvenancedObservation:
    return ProvenancedObservation(
        provider="fake",
        series_id=series,
        observed_at=date.fromisoformat(observed),
        published_at=_utc_midnight(published),
        value=value,
    )


def _utc_midnight(iso_date: str) -> datetime:
    return datetime.combine(
        date.fromisoformat(iso_date),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )


def _generate(series: str, start: str, periods: int, revisions: int) -> list[ProvenancedObservation]:
    """Synthetic vintage matrix: ``periods`` periods, each with ``revisions``
    vintages published on successive days after the period."""
    rows: list[ProvenancedObservation] = []
    period = date.fromisoformat(start)
    base = Decimal("4.00") if series == "DGS10" else Decimal("100.0")
    for idx in range(periods):
        observed = period + timedelta(days=30 * idx)
        for rev in range(revisions):
            published = observed + timedelta(days=2 + rev)
            if rev == 0 and idx % 3 == 0:
                value: Decimal | None = _MISSING
            else:
                value = base + Decimal(rev) * Decimal("0.05") + Decimal(idx) * Decimal("0.01")
            rows.append(_obs(series, observed.isoformat(), published.isoformat(), value))
    return rows


_CANNED: dict[str, list[ProvenancedObservation]] = {
    "DGS10": _generate("DGS10", "2026-05-01", 4, 2),
    "FEDFUNDS": _generate("FEDFUNDS", "2026-05-01", 4, 1),
    "CPIAUCSL": _generate("CPIAUCSL", "2026-05-01", 4, 2),
    "T10Y2Y": _generate("T10Y2Y", "2026-05-01", 4, 1),
}
