"""Tests for ``DistinctTASnapshotRepository``.

The backtest runner re-ingests the same candle timestamp on every replay, and
``TASnapshot`` has no DB uniqueness on ``(symbol, snapshot_timestamp)``, so
duplicate rows can pile up and ``find_in_range`` would otherwise replay each
one, compounding runtime. The distinct repository must collapse duplicates via
``DISTINCT ON (snapshot_timestamp)`` while keeping the same chronological,
inclusive-range contract as the base repository.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from django.utils import timezone as dj_timezone

from apps.technical_analysis.infrastructure.models import TASnapshot as TASnapshotModel
from apps.technical_analysis.infrastructure.repositories import (
    DistinctTASnapshotRepository,
    TASnapshotRepository,
)

pytestmark = pytest.mark.django_db

_UTC = timezone.utc


def _make_snapshot(*, symbol: str, ts: datetime, timeframe: str = "1D", close: str = "100.0") -> TASnapshotModel:
    return TASnapshotModel.objects.create(
        symbol=symbol,
        exchange="NSE",
        timeframe=timeframe,
        indicators={"close": close},
        raw_payload={"ticker": symbol, "close": close, "time": int(ts.timestamp() * 1000)},
        snapshot_timestamp=ts,
    )


class TestDistinctTASnapshotRepository:
    def test_dedupes_duplicate_timestamps(self) -> None:
        ts = datetime(2024, 1, 2, 10, 0, tzinfo=_UTC)
        for close in ("100.0", "100.1", "100.2"):
            _make_snapshot(symbol="RELIANCE", ts=ts, close=close)

        base = TASnapshotRepository().find_in_range(
            "RELIANCE", ts - timedelta(days=1), ts + timedelta(days=1), timeframe="1D"
        )
        distinct = DistinctTASnapshotRepository().find_in_range(
            "RELIANCE", ts - timedelta(days=1), ts + timedelta(days=1), timeframe="1D"
        )

        assert len(base) == 3
        assert len(distinct) == 1
        assert distinct[0].snapshot_timestamp == ts

    def test_preserves_chronological_order_and_inclusive_range(self) -> None:
        base_ts = datetime(2024, 1, 2, 10, 0, tzinfo=_UTC)
        timestamps = [base_ts + timedelta(days=d) for d in (0, 1, 3)]
        for ts in timestamps:
            _make_snapshot(symbol="TCS", ts=ts)
        _make_snapshot(symbol="TCS", ts=timestamps[1])  # duplicate

        distinct = DistinctTASnapshotRepository().find_in_range(
            "TCS", timestamps[0], timestamps[2], timeframe="1D"
        )

        assert [s.snapshot_timestamp for s in distinct] == timestamps

    def test_filters_by_symbol_and_timeframe(self) -> None:
        ts = datetime(2024, 1, 2, 10, 0, tzinfo=_UTC)
        _make_snapshot(symbol="INFY", ts=ts, timeframe="1D")
        _make_snapshot(symbol="INFY", ts=ts, timeframe="15min")
        _make_snapshot(symbol="WIPRO", ts=ts, timeframe="1D")

        distinct = DistinctTASnapshotRepository().find_in_range(
            "INFY", ts - timedelta(days=1), ts + timedelta(days=1), timeframe="1D"
        )
        assert len(distinct) == 1
        assert distinct[0].symbol == "INFY"
        assert distinct[0].timeframe == "1D"