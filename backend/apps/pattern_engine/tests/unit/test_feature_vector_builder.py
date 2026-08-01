from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.market_data.domain.entities import Candle, Instrument
from apps.pattern_engine.infrastructure.feature_vector_builder import (
    build_historical_feature_vector,
    compute_outcome,
)
from core.events.event_types import MarketTrend

TZ = timezone.utc


def _instrument() -> Instrument:
    return Instrument(
        instrument_token=1,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries",
        segment="EQ",
        lot_size=1,
        tick_size=Decimal("0.05"),
        instrument_type="EQ",
    )


def _candles() -> list[Candle]:
    rows = [
        Candle(
            1,
            "1D",
            datetime(2024, 3, 1, 10, 0, tzinfo=TZ),
            Decimal(100),
            Decimal(102),
            Decimal(99),
            Decimal(101),
            1_000_000,
        ),
        Candle(
            1,
            "1D",
            datetime(2024, 3, 2, 10, 0, tzinfo=TZ),
            Decimal(101),
            Decimal(103),
            Decimal(100),
            Decimal(102),
            1_100_000,
        ),
        Candle(
            1,
            "1D",
            datetime(2024, 3, 3, 10, 0, tzinfo=TZ),
            Decimal(102),
            Decimal(105),
            Decimal(101),
            Decimal(104),
            1_300_000,
        ),
        Candle(
            1,
            "1D",
            datetime(2024, 3, 4, 10, 0, tzinfo=TZ),
            Decimal(104),
            Decimal(106),
            Decimal(103),
            Decimal(105),
            1_200_000,
        ),
    ]
    return rows


class FakeCandleRepo:
    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def find_range(self, token, timeframe, from_ts, to_ts) -> list[Candle]:
        return [c for c in self._candles if from_ts <= c.timestamp <= to_ts]


class FakeInstrumentRepo:
    def find_by_symbol(self, symbol) -> Instrument | None:
        return _instrument()


class FakeTARepo:
    def __init__(self, indicators_by_date: dict | None = None) -> None:
        self._data = indicators_by_date or {}

    def find_by_symbol(self, symbol, limit=100) -> list:
        class _Snap:
            pass

        out = []
        for day, indicators in self._data.items():
            snap = _Snap()
            snap.snapshot_timestamp = datetime.combine(
                day, datetime.min.time(), tzinfo=TZ
            )
            snap.indicators = indicators
            out.append(snap)
        return out


class TestBuildHistoricalFeatureVector:
    def test_builds_price_features(self) -> None:
        repo = FakeCandleRepo(_candles())
        vector = build_historical_feature_vector(
            "RELIANCE",
            datetime(2024, 3, 4, 10, 0, tzinfo=TZ),
            candle_repo=repo,
            ta_repo=FakeTARepo(),
            instrument_repo=FakeInstrumentRepo(),
        )
        assert vector is not None
        assert vector.symbol == "RELIANCE"
        # change from 104 -> 105
        assert float(vector.price_change_pct) == pytest.approx(
            float(Decimal(105) / Decimal(104) * Decimal(100) - Decimal(100)), abs=0.001
        )
        # gap from 104 -> 104
        assert float(vector.gap_pct) == pytest.approx(0.0, abs=0.001)
        # volume ratio against 20d avg (not enough candles → window avg)
        assert float(vector.volume_ratio) == pytest.approx(
            float(Decimal(1200000) / Decimal("1133333.333333")), abs=0.001
        )
        assert vector.rsi_14 is None
        assert vector.pcr is None
        assert vector.crude_oil_pct is None

    def test_technical_indicators_when_snapshot_exists(self) -> None:
        repo = FakeCandleRepo(_candles())
        ta_repo = FakeTARepo(
            {
                datetime(2024, 3, 4, tzinfo=TZ).date(): {
                    "rsi_14": 60.5,
                    "macd_histogram": 0.75,
                    "bb_upper": 110.0,
                    "bb_lower": 98.0,
                    "trend": "UPTREND",
                }
            }
        )
        vector = build_historical_feature_vector(
            "RELIANCE",
            datetime(2024, 3, 4, 10, 0, tzinfo=TZ),
            candle_repo=repo,
            ta_repo=ta_repo,
            instrument_repo=FakeInstrumentRepo(),
        )
        assert vector is not None
        assert vector.rsi_14 == Decimal("60.5")
        assert vector.macd_histogram == Decimal("0.75")
        assert vector.trend == MarketTrend.UPTREND
        assert float(vector.bb_position) == pytest.approx(0.5833, abs=0.001)

    def test_returns_none_when_insufficient_candles(self) -> None:
        repo = FakeCandleRepo(_candles()[:1])
        vector = build_historical_feature_vector(
            "RELIANCE",
            datetime(2024, 3, 1, 10, 0, tzinfo=TZ),
            candle_repo=repo,
            ta_repo=FakeTARepo(),
            instrument_repo=FakeInstrumentRepo(),
        )
        assert vector is None

    def test_returns_none_when_no_instrument(self) -> None:
        class NoInstrumentRepo:
            def find_by_symbol(self, symbol) -> None:
                return None

        vector = build_historical_feature_vector(
            "RELIANCE",
            datetime(2024, 3, 4, 10, 0, tzinfo=TZ),
            candle_repo=FakeCandleRepo(_candles()),
            ta_repo=FakeTARepo(),
            instrument_repo=NoInstrumentRepo(),
        )
        assert vector is None


class TestComputeOutcome:
    def test_next_session_change(self) -> None:
        repo = FakeCandleRepo(_candles())
        change, window = compute_outcome(
            "RELIANCE",
            datetime(2024, 3, 3, 10, 0, tzinfo=TZ),
            candle_repo=repo,
            instrument_repo=FakeInstrumentRepo(),
        )
        assert window == 24
        # prev close 104 (2024-03-03) -> next close 105 (2024-03-04)
        assert float(change) == pytest.approx(
            float((Decimal(105) - Decimal(104)) / Decimal(104) * Decimal(100)),
            abs=0.001,
        )

    def test_no_next_session_returns_none(self) -> None:
        repo = FakeCandleRepo(_candles())
        change, window = compute_outcome(
            "RELIANCE",
            datetime(2024, 3, 4, 10, 0, tzinfo=TZ),
            candle_repo=repo,
            instrument_repo=FakeInstrumentRepo(),
        )
        assert change is None
        assert window == 24
