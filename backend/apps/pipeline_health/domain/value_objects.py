"""PIPELINE-HEALTH-1 — domain value objects.

Stage, PipelineHealthStatus and StageExpectation are the pure domain
building blocks of the pipeline health context. None of them touch Django
models; the staleness computation is a pure function of the stage and the
shared market calendar so it can be unit-tested in isolation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum


class Stage(str, Enum):
    """Pipeline stages observed by the health monitor.

    Each member maps one-to-one to an upstream event family the monitor
    subscribes to via ``infrastructure/event_consumers.py``.
    """

    MARKET_DATA = "MARKET_DATA"
    TECHNICAL_ANALYSIS = "TECHNICAL_ANALYSIS"
    INTELLIGENCE = "INTELLIGENCE"
    RULE_ENGINE = "RULE_ENGINE"
    EXECUTION = "EXECUTION"

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(member.value, member.value) for member in cls]


class PipelineHealthStatus(str, Enum):
    """Rolled-up health of the forward paper-trading pipeline."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    STALLED = "STALLED"

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(member.value, member.value) for member in cls]


class StageExpectation:
    """Maximum tolerated silence for a pipeline stage.

    A stage is considered stalled when it has produced no heartbeat for
    longer than its expectation during market hours. Outside market hours
    the expectation is ``None`` — a stage can never be stale while the
    market is closed.

    The market-data expectation is derived from
    ``MARKET_DATA_POLL_INTERVAL_SECONDS * 3`` so the monitor tolerates up
    to two consecutive missed poll cycles plus one heartbeat-cycle delay.
    """

    def __init__(self, stage: Stage, max_silence: timedelta | None) -> None:
        self.stage = stage
        self.max_silence = max_silence

    @property
    def never_stale(self) -> bool:
        """True when the stage can never be marked stale (market closed)."""
        return self.max_silence is None

    @classmethod
    def for_stage(cls, stage: Stage, *, market_open: bool) -> "StageExpectation":
        """Build the expectation for a stage given the market session state.

        Args:
            stage: The pipeline stage.
            market_open: Whether the market is currently in continuous
                trading (``MarketCalendar.is_market_hours()``).

        Returns:
            A ``StageExpectation`` carrying the stage's max silence during
            market hours, or ``None`` (never stale) when the market is shut.
        """
        if not market_open:
            return cls(stage=stage, max_silence=None)

        from django.conf import settings

        if stage == Stage.MARKET_DATA:
            seconds = settings.MARKET_DATA_POLL_INTERVAL_SECONDS * 3
        elif stage == Stage.TECHNICAL_ANALYSIS:
            seconds = settings.TECHNICAL_ANALYSIS_MAX_SILENCE_SECONDS
        elif stage == Stage.INTELLIGENCE:
            seconds = settings.INTELLIGENCE_MAX_SILENCE_SECONDS
        elif stage == Stage.RULE_ENGINE:
            seconds = settings.RULE_ENGINE_MAX_SILENCE_SECONDS
        elif stage == Stage.EXECUTION:
            seconds = settings.EXECUTION_MAX_SILENCE_SECONDS
        else:  # pragma: no cover - exhaustive over the Stage enum
            seconds = settings.MARKET_DATA_POLL_INTERVAL_SECONDS * 3

        return cls(stage=stage, max_silence=timedelta(seconds=seconds))

    def is_stalled(
        self,
        last_event_at: datetime,
        *,
        reference: datetime | None = None,
    ) -> bool:
        """Return True when ``last_event_at`` is older than the expectation.

        Args:
            last_event_at: The most recent heartbeat timestamp (UTC-aware).
            reference: Comparison instant; defaults to now (UTC).

        Returns:
            False when the expectation is ``None`` (never stale) or the
            heartbeat is within the max-silence window; True otherwise.
        """
        if self.max_silence is None:
            return False
        if last_event_at.tzinfo is None:
            raise ValueError(
                f"StageExpectation.is_stalled requires a timezone-aware "
                f"datetime, got: {last_event_at!r}"
            )
        now = reference if reference is not None else datetime.now(timezone.utc)
        return now - last_event_at > self.max_silence
