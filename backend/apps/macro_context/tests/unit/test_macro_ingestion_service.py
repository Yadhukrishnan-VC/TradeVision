"""MACRO-CONTEXT-1 — ingestion service tests.

Covers append-only persistence (revisions preserved), known-missing (``"."``)
rows, re-run idempotency, and per-series error isolation.
"""

from __future__ import annotations

from datetime import date

from apps.macro_context.application.macro_ingestion_service import (
    MacroIngestionService,
)
from apps.macro_context.infrastructure.providers.fake_provider import (
    FakeMacroProvider,
)
from apps.macro_context.tests.conftest import (
    ExplodingMacroProvider,
    FakeMacroObservationRepository,
)


def _service(repository, provider) -> MacroIngestionService:
    return MacroIngestionService(
        provider=provider,
        repository=repository,
        realtime_start=date(2020, 1, 1),
        realtime_end=date(9999, 12, 31),
    )


class TestAppendOnlyIngestion:
    def test_persists_every_vintage_of_every_series(self) -> None:
        repo = FakeMacroObservationRepository()
        summary = _service(repo, FakeMacroProvider()).run()

        assert summary["errors"] == []
        # DGS10: 4 periods x 2 revisions; others: 4 x 1 or 4 x 2.
        assert summary["fetched"] == 4 * 2 + 4 * 1 + 4 * 2 + 4 * 1
        assert summary["inserted"] == summary["fetched"]
        assert repo.count() == summary["fetched"]

    def test_revisions_are_separate_rows(self) -> None:
        repo = FakeMacroObservationRepository()
        _service(repo, FakeMacroProvider()).run()

        dgs10 = repo.observations_for_series("DGS10")
        observed_dates = {row.observed_at for row in dgs10}
        assert len(observed_dates) == 4
        # Each period has its original vintage and one revision.
        for observed in observed_dates:
            period_rows = [r for r in dgs10 if r.observed_at == observed]
            assert len(period_rows) == 2

    def test_known_missing_rows_are_persisted(self) -> None:
        repo = FakeMacroObservationRepository()
        _service(repo, FakeMacroProvider()).run()

        dgs10 = repo.observations_for_series("DGS10")
        missing = [r for r in dgs10 if r.value is None]
        assert missing, "FRED '.' rows must be stored, not dropped"

    def test_rerun_is_idempotent(self) -> None:
        repo = FakeMacroObservationRepository()
        service = _service(repo, FakeMacroProvider())

        first = service.run()
        second = service.run()

        assert second["inserted"] == 0
        assert repo.count() == first["fetched"]

    def test_provider_failure_is_isolated_per_series(self) -> None:
        repo = FakeMacroObservationRepository()
        provider = ExplodingMacroProvider(series_to_fail={"FEDFUNDS"})
        summary = _service(repo, provider).run()

        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["series_id"] == "FEDFUNDS"
        assert summary["inserted"] == 0
        assert repo.count() == 0


class TestIngestionWindows:
    def test_realtime_start_filters_old_vintages(self) -> None:
        full_repo = FakeMacroObservationRepository()
        full = MacroIngestionService(
            provider=FakeMacroProvider(),
            repository=full_repo,
            realtime_start=date(2020, 1, 1),
        ).run()

        filtered_repo = FakeMacroObservationRepository()
        filtered = MacroIngestionService(
            provider=FakeMacroProvider(),
            repository=filtered_repo,
            realtime_start=date(2026, 6, 1),  # only late vintages
        ).run()

        assert 0 < filtered["fetched"] < full["fetched"]
        assert filtered_repo.count() == filtered["fetched"]
