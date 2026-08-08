"""Unit tests for the candle -> TA bridge (Batch M4).

Focus: payload shaping, prev-close/change_pct derivation, the staleness guard,
and the Redis marker's exactly-once semantics. The full event cascade is
covered separately by the E2E integration test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from pytest import MonkeyPatch

from apps.market_data.application.candle_ta_bridge import CandleToTechnicalAnalysisBridge
from apps.market_data.domain.entities import Candle
from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.market_data.infrastructure.models import Instrument as InstrumentModel

NOW = datetime(2026, 8, 8, 7, 0, 0, tzinfo=timezone.utc)

INDICATOR_KEYS = (
    "vwap",
    "ema_20",
    "ema_50",
    "ema_200",
    "atr_14",
    "rsi_14",
    "macd",
    "bb_upper",
    "bb_lower",
    "supertrend_value",
)


class FakeRedis:
    """Minimal dict-backed stand-in for the production Redis client."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def set(self, key: str, value: str) -> None:
        self._store[key] = value


class RecordingIngestion:
    """Stand-in TA ingestion service that records calls instead of ingesting."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = fail

    def ingest(self, payload: dict[str, Any], correlation_id: Any = None) -> object:
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append({"payload": payload, "correlation_id": correlation_id})
        return object()


@pytest.fixture
def fresh_clock(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.market_data.application.candle_ta_bridge.get_now", lambda: NOW
    )


def _seed_instrument(db: Any) -> None:
    InstrumentModel.objects.create(
        instrument_token=1001,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries Ltd",
        segment="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
        instrument_type="EQ",
    )


def _seed_candles(db: Any) -> None:
    _seed_instrument(db)
    CandleModel.objects.create(
        instrument_id=1001,
        timeframe="1min",
        timestamp=NOW - timedelta(seconds=240),
        open=Decimal("100.00"),
        high=Decimal("100.50"),
        low=Decimal("99.50"),
        close=Decimal("100.50"),
        volume=90_000,
    )
    CandleModel.objects.create(
        instrument_id=1001,
        timeframe="1min",
        timestamp=NOW - timedelta(seconds=60),
        open=Decimal("103.00"),
        high=Decimal("104.00"),
        low=Decimal("102.00"),
        close=Decimal("103.00"),
        volume=1_000_000,
    )


def _fresh_candle() -> Candle:
    return Candle(
        instrument_token=1001,
        timeframe="1min",
        timestamp=NOW - timedelta(seconds=60),
        open=Decimal("103.00"),
        high=Decimal("104.00"),
        low=Decimal("102.00"),
        close=Decimal("103.00"),
        volume=1_000_000,
    )


def _bridge(**overrides: Any) -> CandleToTechnicalAnalysisBridge:
    kwargs: dict[str, Any] = {
        "redis_client": FakeRedis(),
        "staleness_seconds": 180,
        "ingestion_service": RecordingIngestion(),
    }
    kwargs.update(overrides)
    return CandleToTechnicalAnalysisBridge(**kwargs)


# ---------------------------------------------------------------------------
# should_ingest — freshness + exactly-once marker
# ---------------------------------------------------------------------------


class TestShouldIngest:
    def test_fresh_and_unseen_is_accepted(self, fresh_clock) -> None:
        bridge = _bridge()
        assert bridge.should_ingest(1001, "1min", NOW - timedelta(seconds=60)) is True

    def test_stale_candle_is_rejected(self, fresh_clock) -> None:
        bridge = _bridge()
        stale = NOW - timedelta(seconds=200)
        assert bridge.should_ingest(1001, "1min", stale) is False

    def test_duplicate_is_rejected_after_marking(self, fresh_clock) -> None:
        bridge = _bridge()
        ts = NOW - timedelta(seconds=60)
        assert bridge.should_ingest(1001, "1min", ts) is True
        bridge.mark_ingested(1001, "1min", ts)
        assert bridge.should_ingest(1001, "1min", ts) is False

    def test_fresh_candle_after_older_ingest_is_accepted(self, fresh_clock) -> None:
        bridge = _bridge()
        old = NOW - timedelta(seconds=120)
        newer = NOW - timedelta(seconds=60)
        bridge.mark_ingested(1001, "1min", old)
        assert bridge.should_ingest(1001, "1min", newer) is True

    def test_corrupt_marker_is_treated_as_unseen(self, fresh_clock) -> None:
        bridge = _bridge()
        redis = bridge._redis
        redis.set(f"{bridge._marker_key(1001, '1min')}", "not-a-timestamp")
        ts = NOW - timedelta(seconds=60)
        assert bridge.should_ingest(1001, "1min", ts) is True


# ---------------------------------------------------------------------------
# build_payload_for_candle — shape, prev-close change_pct, no indicators
# ---------------------------------------------------------------------------


class TestBuildPayload:
    @pytest.mark.django_db
    def test_payload_shape_with_prev_close_and_change_pct(self, db) -> None:
        _seed_candles(db)
        payload = _bridge().build_payload_for_candle(_fresh_candle())

        assert payload["ticker"] == "RELIANCE"
        assert payload["exchange"] == "NSE"
        assert payload["timeframe"] == "1min"
        assert payload["close"] == "103.00"
        assert payload["open"] == "103.00"
        assert payload["high"] == "104.00"
        assert payload["low"] == "102.00"
        assert payload["volume"] == 1_000_000
        assert payload["time"] == int((NOW - timedelta(seconds=60)).timestamp() * 1000)

        assert Decimal(payload["prev_close"]) == Decimal("100.50")
        expected_change = ((Decimal("103.00") - Decimal("100.50")) / Decimal("100.50") * Decimal("100")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        assert Decimal(payload["change_pct"]) == expected_change == Decimal("2.4876")

        for key in INDICATOR_KEYS:
            assert key not in payload, f"indicator key {key!r} must not be invented"

    @pytest.mark.django_db
    def test_payload_without_prev_close_omits_change_fields(self, db) -> None:
        _seed_instrument(db)
        CandleModel.objects.create(
            instrument_id=1001,
            timeframe="1min",
            timestamp=NOW - timedelta(seconds=60),
            open=Decimal("103.00"),
            high=Decimal("104.00"),
            low=Decimal("102.00"),
            close=Decimal("103.00"),
            volume=1_000_000,
        )
        payload = _bridge().build_payload_for_candle(_fresh_candle())

        assert "prev_close" not in payload
        assert "change_pct" not in payload

    @pytest.mark.django_db
    def test_unknown_instrument_raises(self, db) -> None:
        with pytest.raises(ValueError, match="No instrument for token"):
            _bridge().build_payload_for_candle(_fresh_candle())


# ---------------------------------------------------------------------------
# ingest_fresh_candle — end-to-end bridge flow
# ---------------------------------------------------------------------------


class TestIngestFreshCandle:
    @pytest.mark.django_db
    def test_ingests_and_marks_marker(self, db, fresh_clock) -> None:
        _seed_candles(db)
        recording = RecordingIngestion()
        bridge = _bridge(ingestion_service=recording)
        ts = NOW - timedelta(seconds=60)

        candle = bridge.ingest_fresh_candle(1001, "1min", ts)

        assert candle is not None
        assert len(recording.calls) == 1
        assert Decimal(recording.calls[0]["payload"]["change_pct"]) == Decimal("2.4876")
        assert recording.calls[0]["correlation_id"] is not None
        marker = bridge._redis.get(bridge._marker_key(1001, "1min"))
        assert marker is not None

    @pytest.mark.django_db
    def test_same_candle_is_not_reingested(self, db, fresh_clock) -> None:
        _seed_candles(db)
        recording = RecordingIngestion()
        bridge = _bridge(ingestion_service=recording)
        ts = NOW - timedelta(seconds=60)

        bridge.ingest_fresh_candle(1001, "1min", ts)
        second = bridge.ingest_fresh_candle(1001, "1min", ts)

        assert second is None
        assert len(recording.calls) == 1

    @pytest.mark.django_db
    def test_stale_candle_skipped(self, db, fresh_clock) -> None:
        _seed_candles(db)
        recording = RecordingIngestion()
        bridge = _bridge(ingestion_service=recording)

        result = bridge.ingest_fresh_candle(1001, "1min", NOW - timedelta(seconds=200))

        assert result is None
        assert recording.calls == []

    @pytest.mark.django_db
    def test_missing_candle_returns_none_without_ingest(self, db, fresh_clock) -> None:
        _seed_candles(db)
        recording = RecordingIngestion()
        bridge = _bridge(ingestion_service=recording)

        result = bridge.ingest_fresh_candle(1001, "1min", NOW - timedelta(seconds=30))

        assert result is None
        assert recording.calls == []

    @pytest.mark.django_db
    def test_failed_ingestion_does_not_mark_marker(self, db, fresh_clock) -> None:
        _seed_candles(db)
        bridge = _bridge(ingestion_service=RecordingIngestion(fail=True))
        ts = NOW - timedelta(seconds=60)

        with pytest.raises(RuntimeError, match="boom"):
            bridge.ingest_fresh_candle(1001, "1min", ts)

        assert bridge._redis.get(bridge._marker_key(1001, "1min")) is None

    @pytest.mark.django_db
    def test_correlation_id_is_deterministic(self, db, fresh_clock) -> None:
        _seed_candles(db)
        ts = NOW - timedelta(seconds=60)

        recording_a = RecordingIngestion()
        bridge_a = _bridge(ingestion_service=recording_a)
        bridge_a.ingest_fresh_candle(1001, "1min", ts)

        recording_b = RecordingIngestion()
        bridge_b = _bridge(ingestion_service=recording_b)
        bridge_b.ingest_fresh_candle(1001, "1min", ts)

        assert len(recording_a.calls) == 1
        assert len(recording_b.calls) == 1
        assert recording_a.calls[0]["correlation_id"] == recording_b.calls[0]["correlation_id"]