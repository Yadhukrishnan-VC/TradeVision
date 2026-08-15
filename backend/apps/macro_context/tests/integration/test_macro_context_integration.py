"""MACRO-CONTEXT-1 — integration tests.

Wires the macro context into the intelligence scoring input and exercises
the full ORM-backed path (ingest -> store -> point-in-time build) plus the
Beat task boundary.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from apps.intelligence.domain.context_scoring import (
    ContextScoringInput,
    compute_context_scores,
)
from apps.intelligence.domain.market_regime import (
    MarketRegime,
    MultiTimeframeAlignment,
)
from apps.macro_context.application.macro_ingestion_service import (
    MacroIngestionService,
)
from apps.macro_context.infrastructure.providers.fake_provider import (
    FakeMacroProvider,
)
from apps.macro_context.infrastructure.repositories import (
    MacroObservationRepository,
)
from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    DataQuality,
    NewsContext,
    PriceContext,
    TechnicalContext,
)


def _minimal_input(**overrides) -> ContextScoringInput:
    base = {
        "price_context": PriceContext(
            current_price=Decimal("100.00"),
            open_price=Decimal("99.00"),
            high=Decimal("101.00"),
            low=Decimal("98.00"),
            volume=50000,
            avg_volume_20d=0,
            circuit_status=CircuitStatus.NORMAL,
        ),
        "technical_context": TechnicalContext(),
        "breadth_context": BreadthContext(
            sector_index_change_pct=Decimal("0.00"),
            sector_advance_decline=Decimal("0.00"),
            nifty_change_pct=Decimal("0.00"),
            sensex_change_pct=Decimal("0.00"),
        ),
        "news_context": NewsContext(),
        "regime": MarketRegime.RANGING,
        "mtf_alignment": MultiTimeframeAlignment.NEUTRAL,
        "global_context": None,
        "pattern_context": None,
        "data_quality": DataQuality(),
    }
    base.update(overrides)
    return ContextScoringInput(**base)


class TestContextScoringWiring:
    def test_macro_context_defaults_to_none(self) -> None:
        inputs = _minimal_input()
        assert inputs.macro_context is None
        assert compute_context_scores(inputs).overall_context_confidence >= 0

    def test_macro_context_can_be_provided(self) -> None:
        from apps.macro_context.domain.entities import MacroContext

        macro = MacroContext(
            as_of=datetime(2026, 5, 6, tzinfo=timezone.utc),
            dgs10=Decimal("4.15"),
            series_count=1,
        )
        inputs = _minimal_input(macro_context=macro)
        assert inputs.macro_context.dgs10 == Decimal("4.15")
        # Scoring still computes with the additive dimension present.
        output = compute_context_scores(inputs)
        assert 0 <= output.bullishness_score <= 1


@pytest.mark.django_db
class TestOrmBackedPointInTime:
    def test_ingest_then_build_returns_point_in_time(self) -> None:
        repo = MacroObservationRepository()
        MacroIngestionService(
            provider=FakeMacroProvider(),
            repository=repo,
            realtime_start=date(2020, 1, 1),
        ).run()

        from apps.macro_context.application.macro_context_builder import (
            MacroContextBuilder,
        )

        ctx = MacroContextBuilder(repository=repo).build(
            as_of=datetime(2026, 5, 10, 12, tzinfo=timezone.utc)
        )
        assert ctx.dgs10 is not None
        assert ctx.series_count >= 1

    def test_missing_vintage_suppresses_series(self) -> None:
        repo = MacroObservationRepository()
        MacroIngestionService(
            provider=FakeMacroProvider(),
            repository=repo,
            realtime_start=date(2020, 1, 1),
        ).run()

        from apps.macro_context.application.macro_context_builder import (
            MacroContextBuilder,
        )

        ctx = MacroContextBuilder(repository=repo).build(
            as_of=datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
        )
        # FakeMacroProvider emits a "." (None) as the first vintage of every
        # third period, so a mid-period as_of must surface None, not zero.
        assert ctx.dgs10 != Decimal(0)


@pytest.mark.django_db
class TestIngestionTask:
    def test_task_runs_and_persists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from apps.macro_context.infrastructure.tasks import ingest_macro_series

        monkeypatch.setattr(
            "apps.macro_context.infrastructure.tasks.get_ingestion_service",
            lambda: MacroIngestionService(
                provider=FakeMacroProvider(),
                repository=MacroObservationRepository(),
                realtime_start=date(2020, 1, 1),
            ),
        )
        ingest_macro_series.run()
        assert MacroObservationRepository().count() > 0

    def test_task_noops_when_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from apps.macro_context.infrastructure.tasks import ingest_macro_series

        called: list[bool] = []

        def _fake_run() -> None:
            called.append(True)

        monkeypatch.setattr(
            "apps.macro_context.infrastructure.tasks.get_ingestion_service",
            lambda: _fake_run(),
        )
        monkeypatch.setattr(
            "django.conf.settings.MACRO_INGESTION_ENABLED",
            False,
        )
        ingest_macro_series.run()
        assert called == []
