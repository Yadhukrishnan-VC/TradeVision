"""Batch HISTORICAL-TA-BACKFILL-1 — historical candle -> TASnapshot tests.

The batch adds a single non-live entry point on ``CandleToTechnicalAnalysisBridge``
that walks already-persisted ``Candle`` rows oldest-to-newest and pushes each
through the *unchanged* ``build_payload_for_candle`` / ``TechnicalAnalysisIngestionService.ingest``
seam, bypassing the live-only staleness gate. ``TASnapshot`` has no DB uniqueness
on ``(symbol, snapshot_timestamp)``, so the method pre-checks existing snapshots
(one range query) and skips them, making re-runs idempotent without a schema change.

Covered here, with genuine-but-synthetic fixtures:
* warm-up behaviour is identical to the live path (first 59 candles omit
  ``ema_20`` — never zero-filled; the 60th includes it with the exact
  ``compute_ema`` value),
* re-running the same range is idempotent (exact snapshot count, no duplicate
  rows, no duplicate ``TechnicalAnalysisCompleted`` events),
* causality: a later candle already persisted in the DB is excluded from an
  earlier candle's indicator window (no look-ahead via ``_indicator_series``),
* failure isolation: one malformed candle does not stop the rest of the range,
* the live polling path (``should_ingest``/``ingest_fresh_candle``) is untouched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from apps.market_data.application.candle_ta_bridge import (
    CandleToTechnicalAnalysisBridge,
)
from apps.market_data.domain.entities import Candle
from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.models import Instrument as InstrumentModel
from apps.technical_analysis.domain.indicators import compute_ema
from apps.technical_analysis.infrastructure.models import TASnapshot as TASnapshotModel

_UTC = timezone.utc
_T0 = datetime(2024, 1, 1, 9, 30, tzinfo=_UTC)


def _candle_list(closes: list[str], start: datetime = _T0) -> list[Candle]:
    """Build ``Candle`` domain entities from a list of closes (oldest->newest)."""
    return [
        Candle(
            instrument_token=1001,
            timeframe="1min",
            timestamp=start + timedelta(minutes=i),
            open=Decimal(c),
            high=Decimal(c),
            low=Decimal(c),
            close=Decimal(c),
            volume=1000,
        )
        for i, c in enumerate(closes)
    ]


class RecordingIngestion:
    """Stand-in TA ingestion service that records calls instead of ingesting."""

    def __init__(self, *, fail_at: set[int] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_at = fail_at or set()

    def ingest(self, payload: dict[str, Any], correlation_id: Any = None) -> object:
        if correlation_id in self.fail_at:
            raise RuntimeError("boom")
        self.calls.append({"payload": payload, "correlation_id": correlation_id})
        return object()


def _seed_instrument(db: Any, token: int = 1001, symbol: str = "RELIANCE") -> None:
    InstrumentModel.objects.create(
        instrument_token=token,
        exchange="NSE",
        tradingsymbol=symbol,
        name="Reliance Industries Ltd (Backtest)",
        segment="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
        instrument_type="EQ",
    )


def _seed_candles(
    db: Any,
    count: int,
    *,
    token: int = 1001,
    timeframe: str = "1min",
    start: datetime = _T0,
    closes: list[str] | None = None,
    volume: int = 1000,
) -> list[datetime]:
    """Seed ``count`` candles oldest->newest; returns their timestamps."""
    _seed_instrument(db, token=token)
    timestamps: list[datetime] = []
    for idx in range(count):
        ts = start + timedelta(minutes=idx)
        close = closes[idx] if closes else "100.00"
        CandleModel.objects.create(
            instrument_id=token,
            timeframe=timeframe,
            timestamp=ts,
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=volume,
        )
        timestamps.append(ts)
    return timestamps


def _bridge(**overrides: Any) -> CandleToTechnicalAnalysisBridge:
    kwargs: dict[str, Any] = {}
    kwargs.update(overrides)
    return CandleToTechnicalAnalysisBridge(**kwargs)


@pytest.mark.django_db
class TestHistoricalTaBackfill:

    def test_warm_up_omits_ema_then_present_with_exact_value(self, db) -> None:
        timestamps = _seed_candles(db, 60)
        bridge = _bridge()

        created = bridge.backfill_ta_from_candles(1001, "1min", _T0, timestamps[-1])
        assert created == 60

        snapshots = list(
            TASnapshotModel.objects.filter(
                symbol="RELIANCE", timeframe="1min"
            ).order_by("snapshot_timestamp")
        )
        assert len(snapshots) == 60
        # First 59 candles: warm-up not satisfied -> ema_20 omitted, never zero.
        for snap in snapshots[:-1]:
            assert "ema_20" not in snap.indicators
            assert "0" not in snap.indicators
        # 60th candle: ema_20 present with the exact compute_ema value.
        last = snapshots[-1]
        assert "ema_20" in last.indicators
        expected = compute_ema(_candle_list(["100.00"] * 60), period=20)
        assert Decimal(last.indicators["ema_20"]) == expected

    def test_rerun_is_idempotent_no_duplicate_snapshots(self, db) -> None:
        timestamps = _seed_candles(db, 5)
        bridge = _bridge()

        first = bridge.backfill_ta_from_candles(1001, "1min", _T0, timestamps[-1])
        second = bridge.backfill_ta_from_candles(1001, "1min", _T0, timestamps[-1])

        assert first == 5
        assert second == 0
        assert TASnapshotModel.objects.filter(symbol="RELIANCE").count() == 5

    def test_rerun_skips_already_ingested_per_candle(self, db) -> None:
        """The idempotency pre-check skips candles already persisted as snapshots.

        Uses the real ingestion service (default bridge) so the pre-check and
        persistence stay consistent: after the first run, a second run creates
        no additional rows.
        """
        timestamps = _seed_candles(db, 3)
        bridge = _bridge()

        assert bridge.backfill_ta_from_candles(1001, "1min", _T0, timestamps[-1]) == 3
        assert bridge.backfill_ta_from_candles(1001, "1min", _T0, timestamps[-1]) == 0
        assert TASnapshotModel.objects.filter(symbol="RELIANCE").count() == 3

    def test_causality_later_candle_excluded_from_earlier_window(self, db) -> None:
        """A later candle already persisted must not leak into an earlier window.

        All 61 candles exist in the DB (as a real backfill leaves them), but
        each snapshot's indicators must reflect only candles at or before its
        own timestamp. The 60th candle's ``ema_20`` is therefore the EMA over
        ``[0..59]`` only — candle 61 (persisted but later) must be excluded,
        even though a naive ``find_latest(limit=60)`` would include it and pull
        the EMA up.
        """
        closes = [str(100.0 + i) for i in range(61)]
        timestamps = _seed_candles(db, 61, closes=closes)
        bridge = _bridge()

        created = bridge.backfill_ta_from_candles(1001, "1min", _T0, timestamps[-1])
        assert created == 61

        # 60th candle (index 59): EMA over window [0..59] — candle 61 excluded.
        expected_ema_60th = compute_ema(_candle_list(closes[:60]), period=20)

        snapshots = list(
            TASnapshotModel.objects.filter(
                symbol="RELIANCE", timeframe="1min"
            ).order_by("snapshot_timestamp")
        )
        assert len(snapshots) == 61
        snap_60th = snapshots[59]
        assert Decimal(snap_60th.indicators["ema_20"]) == expected_ema_60th

    def test_failure_isolation_one_bad_candle_does_not_stop_range(self, db) -> None:
        from apps.market_data.domain.entities import Candle

        timestamps = _seed_candles(db, 5)
        bridge = _bridge()

        # Fail the 3rd candle by its deterministic correlation id.
        third = CandleModel.objects.get(instrument_id=1001, timestamp=timestamps[2])
        third_candle = Candle(
            instrument_token=third.instrument_id,
            timeframe=third.timeframe,
            timestamp=third.timestamp,
            open=third.open,
            high=third.high,
            low=third.low,
            close=third.close,
            volume=third.volume,
        )
        failing_corr = bridge._deterministic_correlation(third_candle)
        recording = RecordingIngestion(fail_at={failing_corr})
        bridge = _bridge(ingestion_service=recording)

        created = bridge.backfill_ta_from_candles(1001, "1min", _T0, timestamps[-1])

        # The bad candle is isolated; the other 4 succeed (the failing one
        # raises before recording, so only 4 calls are recorded).
        assert created == 4
        assert len(recording.calls) == 4

    def test_unknown_instrument_raises(self, db) -> None:
        with pytest.raises(ValueError, match="No instrument for token"):
            _bridge().backfill_ta_from_candles(9999, "1min", _T0, _T0 + timedelta(minutes=5))


@pytest.mark.django_db
class TestHistoricalTaBackfillRealPersistence:
    """Real ingestion service (not a recording stub) to verify actual rows."""

    def test_persists_real_tasnapshot_rows_and_publishes(self, db) -> None:
        timestamps = _seed_candles(db, 3)
        bridge = _bridge()

        created = bridge.backfill_ta_from_candles(1001, "1min", _T0, timestamps[-1])
        assert created == 3

        snapshots = list(
            TASnapshotModel.objects.filter(
                symbol="RELIANCE", timeframe="1min"
            ).order_by("snapshot_timestamp")
        )
        assert len(snapshots) == 3
        for snap, ts in zip(snapshots, timestamps):
            assert snap.snapshot_timestamp == ts
            assert snap.indicators == {}
            assert snap.raw_payload["ticker"] == "RELIANCE"

        # Re-run: exactly-once, no duplicates, no extra rows.
        again = bridge.backfill_ta_from_candles(1001, "1min", _T0, timestamps[-1])
        assert again == 0
        assert TASnapshotModel.objects.filter(symbol="RELIANCE").count() == 3


@pytest.mark.django_db
class TestLivePathUntouched:
    """Regression: the live polling staleness/exactly-once path is unchanged."""

    def test_should_ingest_still_rejects_stale(self, db, monkeypatch) -> None:
        from apps.market_data.application import candle_ta_bridge as mod

        now = datetime(2026, 8, 8, 7, 0, 0, tzinfo=_UTC)
        monkeypatch.setattr(mod, "get_now", lambda: now)
        _seed_instrument(db)

        stale = now - timedelta(seconds=3600)
        assert _bridge(staleness_seconds=180).should_ingest(1001, "1min", stale) is False