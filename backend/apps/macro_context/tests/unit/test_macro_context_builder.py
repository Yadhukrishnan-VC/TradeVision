"""MACRO-CONTEXT-1 — point-in-time correctness tests (test-first).

``MacroContextBuilder.build(as_of=...)`` must reconstruct the macro state a
trader could have KNOWN at ``as_of``, never a value that was only released
later. The canned vintage matrix below exercises every revision subtlety:

- ``observed_at`` = the period the value describes.
- ``published_at`` = the moment a specific vintage became public.
- A FRED ``"."`` (missing) row is stored with ``value=None`` and is NOT a
  zero — it must suppress the series until a real value is released, so a
  ``build`` that lands after a missing row but before the revision must
  return ``None`` rather than a stale earlier value.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.macro_context.application.macro_context_builder import (
    MacroContextBuilder,
)
from apps.macro_context.domain.entities import MacroContext, ProvenancedObservation

DGS10 = "DGS10"
FEDFUNDS = "FEDFUNDS"
CPIAUCSL = "CPIAUCSL"
T10Y2Y = "T10Y2Y"


def _utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


def _obs(
    series_id: str,
    observed: tuple[int, int, int],
    published: tuple[int, int, int],
    value: Decimal | None,
) -> ProvenancedObservation:
    return ProvenancedObservation(
        provider="fred",
        series_id=series_id,
        observed_at=_utc(*observed).date(),
        published_at=_utc(*published),
        value=value,
    )


class FakeMacroObservationRepository:
    """In-memory port double honouring the published_at/observed_at windows."""

    def __init__(self, rows: list[ProvenancedObservation]) -> None:
        self._rows = list(rows)

    def observations_for_series(
        self,
        series_id: str,
        *,
        published_at_lte: datetime | None = None,
        observed_at_lte: object | None = None,
    ) -> list[ProvenancedObservation]:
        rows = [r for r in self._rows if r.series_id == series_id]
        if published_at_lte is not None:
            rows = [r for r in rows if r.published_at <= published_at_lte]
        if observed_at_lte is not None:
            rows = [r for r in rows if r.observed_at <= observed_at_lte]
        return rows


# DGS10 vintage matrix — two revisions on 2026-05-01 plus a "." gap that is
# later filled by a revision on 2026-06-09.
_DGS10_VINTAGES = [
    _obs(DGS10, (2026, 5, 1), (2026, 5, 2), Decimal("4.20")),
    _obs(DGS10, (2026, 5, 1), (2026, 5, 6), Decimal("4.15")),
    _obs(DGS10, (2026, 5, 15), (2026, 5, 16), Decimal("4.10")),
    _obs(DGS10, (2026, 6, 1), (2026, 6, 3), None),  # FRED "." — known missing
    _obs(DGS10, (2026, 6, 1), (2026, 6, 9), Decimal("4.05")),
]


def _seed() -> FakeMacroObservationRepository:
    rows = list(_DGS10_VINTAGES)
    # FEDFUNDS — single steady vintage, no revisions.
    rows.append(_obs(FEDFUNDS, (2026, 5, 1), (2026, 5, 2), Decimal("5.50")))
    # CPIAUCSL — a permanently missing row after a real value.
    rows.append(_obs(CPIAUCSL, (2026, 4, 1), (2026, 5, 12), Decimal("315.123")))
    rows.append(_obs(CPIAUCSL, (2026, 5, 1), (2026, 6, 12), None))
    return FakeMacroObservationRepository(rows)


@pytest.fixture
def builder() -> MacroContextBuilder:
    return MacroContextBuilder(repository=_seed())


class TestPointInTime:
    def test_returns_the_vintage_published_by_as_of(self, builder: MacroContextBuilder) -> None:
        ctx = builder.build(as_of=_utc(2026, 5, 3, 12))
        assert ctx.dgs10 == Decimal("4.20")
        assert ctx.series_count == 2  # DGS10 + FEDFUNDS both known

    def test_late_as_of_uses_latest_revision(self, builder: MacroContextBuilder) -> None:
        ctx = builder.build(as_of=_utc(2026, 5, 6, 12))
        assert ctx.dgs10 == Decimal("4.15")

    def test_as_of_before_revision_keeps_earlier_value(self, builder: MacroContextBuilder) -> None:
        ctx = builder.build(as_of=_utc(2026, 5, 5, 12))
        assert ctx.dgs10 == Decimal("4.20")

    def test_missing_row_suppresses_series_until_revision(self, builder: MacroContextBuilder) -> None:
        ctx = builder.build(as_of=_utc(2026, 6, 5, 12))
        assert ctx.dgs10 is None
        assert ctx.cpiaucsl == Decimal("315.123")  # its ".", not yet released

    def test_revision_that_fills_missing_value(self, builder: MacroContextBuilder) -> None:
        ctx = builder.build(as_of=_utc(2026, 6, 10, 12))
        assert ctx.dgs10 == Decimal("4.05")

    def test_aggregates_all_series_for_a_single_as_of(self, builder: MacroContextBuilder) -> None:
        ctx = builder.build(as_of=_utc(2026, 5, 3, 12))
        assert ctx.dgs10 == Decimal("4.20")
        assert ctx.fedfunds == Decimal("5.50")
        assert ctx.cpiaucsl is None  # not released until 2026-05-12
        assert ctx.t10y2y is None  # no data at all
        assert ctx.series_count == 2

    def test_empty_series_yields_none(self) -> None:
        ctx = MacroContextBuilder(
            repository=FakeMacroObservationRepository([_obs(T10Y2Y, (2026, 5, 1), (2026, 5, 2), None)])
        ).build(as_of=_utc(2026, 6, 1, 12))
        assert ctx.t10y2y is None
        assert ctx.series_count == 0


class TestMacroContextContract:
    def test_as_of_is_recorded_on_the_context(self, builder: MacroContextBuilder) -> None:
        ctx = builder.build(as_of=_utc(2026, 5, 6, 12))
        assert ctx.as_of == _utc(2026, 5, 6, 12)

    def test_is_a_frozen_dataclass(self, builder: MacroContextBuilder) -> None:
        from dataclasses import FrozenInstanceError

        ctx = builder.build(as_of=_utc(2026, 5, 6, 12))
        assert isinstance(ctx, MacroContext)
        with pytest.raises(FrozenInstanceError):
            ctx.dgs10 = Decimal("9.99")  # type: ignore[misc]
