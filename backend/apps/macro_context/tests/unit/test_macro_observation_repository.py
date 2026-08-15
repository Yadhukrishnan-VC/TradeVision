"""MACRO-CONTEXT-1 — ORM repository tests (PostgreSQL test DB).

Verifies the append-only constraint, idempotent upserts, and the SQL-level
point-in-time windows against the real ``MacroObservation`` table.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from apps.macro_context.infrastructure.models import MacroObservation
from apps.macro_context.infrastructure.repositories import (
    MacroObservationRepository,
)
from apps.macro_context.tests.conftest import make_observation


@pytest.mark.django_db
class TestAppendOnlyStore:
    def test_inserts_rows_and_counts(self) -> None:
        repo = MacroObservationRepository()
        inserted = repo.upsert_many(
            [
                make_observation("DGS10", "2026-05-01", "2026-05-02", "4.20"),
                make_observation("DGS10", "2026-05-01", "2026-05-06", "4.15"),
            ]
        )
        assert inserted == 2
        assert repo.count() == 2

    def test_rerun_inserts_nothing_new(self) -> None:
        repo = MacroObservationRepository()
        rows = [make_observation("DGS10", "2026-05-01", "2026-05-02", "4.20")]
        assert repo.upsert_many(rows) == 1
        assert repo.upsert_many(rows) == 0
        assert repo.count() == 1

    def test_value_can_be_null_for_known_missing(self) -> None:
        repo = MacroObservationRepository()
        repo.upsert_many([make_observation("DGS10", "2026-06-01", "2026-06-03", None)])
        row = MacroObservation.objects.get()
        assert row.value is None

    def test_revision_is_separate_row(self) -> None:
        repo = MacroObservationRepository()
        repo.upsert_many(
            [
                make_observation("DGS10", "2026-05-01", "2026-05-02", "4.20"),
                make_observation("DGS10", "2026-05-01", "2026-05-06", "4.15"),
            ]
        )
        assert repo.count() == 2


@pytest.mark.django_db
class TestPointInTimeWindows:
    @pytest.fixture(autouse=True)
    def _seed(self) -> None:
        MacroObservationRepository().upsert_many(
            [
                make_observation("DGS10", "2026-05-01", "2026-05-02", "4.20"),
                make_observation("DGS10", "2026-05-01", "2026-05-06", "4.15"),
                make_observation("DGS10", "2026-05-15", "2026-05-16", "4.10"),
            ]
        )

    def test_published_window_excludes_future_vintages(self) -> None:
        rows = MacroObservationRepository().observations_for_series(
            "DGS10",
            published_at_lte=datetime(2026, 5, 5, tzinfo=timezone.utc),
        )
        # Only the 2026-05-02 vintage is known by 2026-05-05; the 4.15
        # revision (published 05-06) must not leak in.
        assert len(rows) == 1
        assert rows[0].value == Decimal("4.20")

    def test_observed_window_excludes_future_periods(self) -> None:
        rows = MacroObservationRepository().observations_for_series(
            "DGS10",
            observed_at_lte=date(2026, 5, 10),
        )
        observed = {r.observed_at for r in rows}
        assert observed == {date(2026, 5, 1)}

    def test_full_window_returns_every_vintage(self) -> None:
        rows = MacroObservationRepository().observations_for_series("DGS10")
        assert len(rows) == 3

    def test_latest_published_at(self) -> None:
        latest = MacroObservationRepository().latest_published_at("DGS10")
        assert latest == datetime(2026, 5, 16, tzinfo=timezone.utc)

    def test_latest_published_at_none_for_empty_series(self) -> None:
        assert MacroObservationRepository().latest_published_at("NOPE") is None
