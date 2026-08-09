"""Unit tests for the candle -> TA bridge (Batch M4).

Focus: payload shaping, prev-close/change_pct derivation, the staleness guard,
and the Redis marker's exactly-once semantics. The full event cascade is
covered separately by the E2E integration test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pytest import MonkeyPatch

_IST = ZoneInfo("Asia/Kolkata")

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


# ---------------------------------------------------------------------------
# Batch M5 — indicator population, warm-up, session-boundary VWAP
# ---------------------------------------------------------------------------


class FakeM5Calendar:
    """Trading-day calendar stand-in used only for assertable session data."""

    @staticmethod
    def is_trading_day(day: object) -> bool:
        return True


def _utc_from_ist(day: Any, hh: int, mm: int) -> datetime:
    day_date = day.date() if isinstance(day, datetime) else day
    return datetime.combine(day_date, datetime.min.time().replace(hour=hh, minute=mm), tzinfo=_IST).astimezone(
        timezone.utc
    )


def _seed_m5_history(
    db: Any,
    count: int,
    *,
    close: str = "100.00",
    high: str = "100.50",
    low: str = "99.50",
    volume: int = 1000,
    start_ts: datetime | None = None,
) -> datetime:
    """Seed ``1min`` candles (oldest→newest) and return the last timestamp."""
    _seed_instrument(db)
    ts = start_ts or (NOW - timedelta(minutes=count))
    for idx in range(count):
        CandleModel.objects.create(
            instrument_id=1001,
            timeframe="1min",
            timestamp=ts + timedelta(minutes=idx),
            open=Decimal(close),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            volume=volume,
        )
    return ts + timedelta(minutes=count - 1)


def _seed_m5_candle(ts: datetime) -> Candle:
    return Candle(
        instrument_token=1001,
        timeframe="1min",
        timestamp=ts,
        open=Decimal("100.00"),
        high=Decimal("100.50"),
        low=Decimal("99.50"),
        close=Decimal("100.00"),
        volume=1000,
    )


def _seed_session_open(db: Any, day: datetime.date) -> datetime:
    """Seed the 09:15 IST opening 15-min candle; returns its UTC timestamp."""
    open_utc = _utc_from_ist(day, 9, 15)
    CandleModel.objects.create(
        instrument_id=1001,
        timeframe="15min",
        timestamp=open_utc,
        open=Decimal("100.00"),
        high=Decimal("100.50"),
        low=Decimal("99.50"),
        close=Decimal("100.00"),
        volume=1000,
    )
    return open_utc


def _bridge_with_session_facts(**overrides: Any) -> CandleToTechnicalAnalysisBridge:
    from apps.market_data.application.session_facts_service import SessionFactsService

    session_facts = SessionFactsService(calendar=FakeM5Calendar())
    kwargs: dict[str, Any] = {
        "redis_client": FakeRedis(),
        "staleness_seconds": 180,
        "ingestion_service": RecordingIngestion(),
        "session_facts": session_facts,
    }
    kwargs.update(overrides)
    return CandleToTechnicalAnalysisBridge(**kwargs)


class TestM5Indicators:
    def test_sufficient_history_emits_all_indicators(self, db) -> None:
        day = NOW.astimezone(_IST).date()
        _seed_instrument(db)
        for i in range(60):
            CandleModel.objects.create(
                instrument_id=1001,
                timeframe="1min",
                timestamp=_utc_from_ist(day, 9, 16) + timedelta(minutes=i),
                open=Decimal("100.00"),
                high=Decimal("100.50"),
                low=Decimal("99.50"),
                close=Decimal("100.00"),
                volume=1000,
            )
        _seed_session_open(db, day)
        last_ts = _utc_from_ist(day, 9, 16) + timedelta(minutes=59)
        payload = _bridge_with_session_facts().build_payload_for_candle(_seed_m5_candle(last_ts))
        self._assert_all_indicator_keys(payload)

    def test_insufficient_history_omits_indicator_keys(self, db) -> None:
        ts = _seed_m5_history(db, count=14)
        payload = _bridge().build_payload_for_candle(_seed_m5_candle(ts))
        for key in ("ema_20", "atr_14", "bb_upper", "rsi_14"):
            assert key not in payload, f"{key!r} must be omitted on insufficient history"

    def test_rsi_boundary_14_absent_15_present(self, db) -> None:
        day = NOW.astimezone(_IST).date()
        _seed_instrument(db)
        closes = [str(100.0 + i) for i in range(14)]
        for i, c in enumerate(closes):
            CandleModel.objects.create(
                instrument_id=1001,
                timeframe="1min",
                timestamp=_utc_from_ist(day, 9, 16) + timedelta(minutes=i),
                open=Decimal(c),
                high=Decimal(c),
                low=Decimal(c),
                close=Decimal(c),
                volume=1000,
            )
        ts_14 = _utc_from_ist(day, 9, 16) + timedelta(minutes=13)
        payload_14 = _bridge().build_payload_for_candle(_seed_m5_candle(ts_14))
        assert "rsi_14" not in payload_14

        CandleModel.objects.create(
            instrument_id=1001,
            timeframe="1min",
            timestamp=_utc_from_ist(day, 9, 16) + timedelta(minutes=14),
            open=Decimal("114"),
            high=Decimal("114"),
            low=Decimal("114"),
            close=Decimal("114"),
            volume=1000,
        )
        ts_15 = _utc_from_ist(day, 9, 16) + timedelta(minutes=14)
        payload_15 = _bridge().build_payload_for_candle(_seed_m5_candle(ts_15))
        assert "rsi_14" in payload_15
        assert Decimal(payload_15["rsi_14"]) == Decimal("100")

    def test_rsi_absent_on_flat_series(self, db) -> None:
        # 60 candles all flat: RSI is the undefined 0/0 reading -> None,
        # so the key must be omitted (never a fabricated zero/50).
        ts = _seed_m5_history(db, 60)
        payload = _bridge().build_payload_for_candle(_seed_m5_candle(ts))
        assert "rsi_14" not in payload

    def test_rsi_payload_key_and_serialization(self, db) -> None:
        day = NOW.astimezone(_IST).date()
        _seed_instrument(db)
        for i in range(60):
            close = Decimal("100") + Decimal(i) * Decimal("1")
            CandleModel.objects.create(
                instrument_id=1001,
                timeframe="1min",
                timestamp=_utc_from_ist(day, 9, 16) + timedelta(minutes=i),
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1000,
            )
        last_ts = _utc_from_ist(day, 9, 16) + timedelta(minutes=59)
        payload = _bridge().build_payload_for_candle(_seed_m5_candle(last_ts))
        assert "rsi_14" in payload
        # stringified exact Decimal, never a fabricated 0
        assert payload["rsi_14"] == str(Decimal("100"))

    def test_ema_decision_c_waits_for_sixty(self, db) -> None:
        # 20 candles satisfy the math seed but Decision C guards at 60.
        ts = _seed_m5_history(db, 20)
        payload = _bridge().build_payload_for_candle(_seed_m5_candle(ts))
        assert "ema_20" not in payload
        assert "atr_14" in payload  # 20 >= 15
        assert "bb_upper" in payload  # 20 >= 20

    def test_indicator_values_are_deterministic(self, db) -> None:
        ts = _seed_m5_history(db, 60)
        bridge = _bridge()
        assert bridge.build_payload_for_candle(_seed_m5_candle(ts)) == bridge.build_payload_for_candle(
            _seed_m5_candle(ts)
        )

    def test_vwap_session_reset(self, db) -> None:
        """VWAP must NOT carry previous-session candles even when they sit in
        the shared 60-candle history — the session slice wins."""
        day = NOW.astimezone(_IST).date()
        prev_day = day - timedelta(days=1)

        _seed_instrument(db)
        # previous session: 10 candles @ 200 (would pull a naive VWAP up)
        for idx in range(10):
            prev_ts = _utc_from_ist(prev_day, 9, 20) + timedelta(minutes=idx)
            CandleModel.objects.create(
                instrument_id=1001,
                timeframe="1min",
                timestamp=prev_ts,
                open=Decimal("200.00"),
                high=Decimal("201.00"),
                low=Decimal("199.00"),
                close=Decimal("200.00"),
                volume=1000,
            )

        # current session: 50 candles @ 100 + the 15m opening candle
        _seed_session_open(db, day)
        for i in range(50):
            CandleModel.objects.create(
                instrument_id=1001,
                timeframe="1min",
                timestamp=_utc_from_ist(day, 9, 16) + timedelta(minutes=i),
                open=Decimal("100.00"),
                high=Decimal("100.50"),
                low=Decimal("99.50"),
                close=Decimal("100.00"),
                volume=1000,
            )
        last_current = _utc_from_ist(day, 9, 16) + timedelta(minutes=49)

        payload = _bridge_with_session_facts().build_payload_for_candle(_seed_m5_candle(last_current))
        # Shared EMA60 window includes the 200s, so EMA is pulled up...
        assert Decimal(payload["ema_20"]) > Decimal("100")
        # ...but the VWAP session slice is exactly the current session at 100.
        assert Decimal(payload["vwap"]) == Decimal("100")

    @staticmethod
    def _assert_all_indicator_keys(payload: dict[str, Any]) -> None:
        for key in ("vwap", "ema_20", "atr_14", "bb_upper"):
            assert key in payload, f"{key!r} must be emitted with sufficient history"
            assert Decimal(payload[key]) > 0