from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.pipeline_health.domain.value_objects import (
    PipelineHealthStatus,
    Stage,
    StageExpectation,
)


class TestStageExpectation:
    @pytest.mark.parametrize(
        ("stage", "expectation_seconds"),
        [
            (Stage.MARKET_DATA, 180),  # 60s poll * 3 (default)
            (Stage.TECHNICAL_ANALYSIS, 300),
            (Stage.INTELLIGENCE, 300),
            (Stage.RULE_ENGINE, 300),
            (Stage.EXECUTION, 600),
        ],
    )
    def test_market_open_expectations(
        self, stage: Stage, expectation_seconds: int
    ) -> None:
        expectation = StageExpectation.for_stage(stage, market_open=True)

        assert expectation.never_stale is False
        assert expectation.max_silence == timedelta(seconds=expectation_seconds)

    def test_market_closed_is_never_stale(self) -> None:
        for stage in Stage:
            expectation = StageExpectation.for_stage(stage, market_open=False)
            assert expectation.never_stale is True
            assert expectation.max_silence is None

    def test_is_stalled_when_older_than_expectation(self) -> None:
        expectation = StageExpectation.for_stage(Stage.MARKET_DATA, market_open=True)
        now = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)

        assert expectation.is_stalled(now - timedelta(seconds=181), reference=now)

    def test_not_stalled_when_within_expectation(self) -> None:
        expectation = StageExpectation.for_stage(Stage.MARKET_DATA, market_open=True)
        now = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)

        assert not expectation.is_stalled(now - timedelta(seconds=180), reference=now)

    def test_never_stale_when_market_closed(self) -> None:
        expectation = StageExpectation.for_stage(Stage.MARKET_DATA, market_open=False)
        now = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)

        assert not expectation.is_stalled(now - timedelta(hours=5), reference=now)

    def test_naive_datetime_raises(self) -> None:
        expectation = StageExpectation.for_stage(Stage.MARKET_DATA, market_open=True)

        with pytest.raises(ValueError):
            expectation.is_stalled(datetime(2026, 8, 11, 9, 30, 0))


class TestPipelineHealthStatus:
    def test_choices_are_unique(self) -> None:
        values = [value for value, _ in PipelineHealthStatus.choices()]
        assert values == ["HEALTHY", "DEGRADED", "STALLED"]

    def test_stage_choices(self) -> None:
        values = [value for value, _ in Stage.choices()]
        assert values == [
            "MARKET_DATA",
            "TECHNICAL_ANALYSIS",
            "INTELLIGENCE",
            "RULE_ENGINE",
            "EXECUTION",
        ]
