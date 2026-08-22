"""LIVE-PAPER-DRESS-REHEARSAL-1 — TickToCandleAggregator unit tests.

Pure bucketing logic: minute rollover, OHLC extremes, cumulative-volume
deltas, flush, and bad-token tolerance. Persistence is observed through a
recorded fake instead of the DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from apps.market_data.application.tick_to_candle_aggregator import (
    TickToCandleAggregator,
)


class _FakeQuote:
    def __init__(self, symbol: str, ltp: str, volume: int | None, tick_at: datetime):
        self.symbol = symbol
        self.ltp = Decimal(ltp)
        self.volume = volume
        self.tick_at = tick_at


def _quote(price: str, cum_volume: int | None, minute: int, second: int = 0) -> _FakeQuote:
    return _FakeQuote(
        "token:123",
        price,
        cum_volume,
        datetime(2026, 8, 22, 9, minute, second, tzinfo=timezone.utc),
    )


@pytest.fixture
def persisted(monkeypatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class _Repo:
        def upsert(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    monkeypatch.setattr(
        "apps.market_data.infrastructure.repositories.CandleRepository",
        lambda: _Repo(),
    )
    return calls


class TestBucketing:
    def test_single_minute_bucket_ohlc_extremes(self, persisted) -> None:
        agg = TickToCandleAggregator(timeframe="1min", on_candle=lambda *_: None)
        agg.handle_quote(_quote("100", 500, 0))
        agg.handle_quote(_quote("110", 520, 0, second=20))
        agg.handle_quote(_quote("95", 530, 0, second=40))
        assert persisted == []  # still in flight

        flushed = agg.flush()
        assert flushed == 1
        assert len(persisted) == 1
        row = persisted[0]
        assert row["instrument_token"] == 123
        assert row["timeframe"] == "1min"
        assert row["open"] == Decimal("100")
        assert row["high"] == Decimal("110")
        assert row["low"] == Decimal("95")
        assert row["close"] == Decimal("95")
        # First tick anchors the cumulative counter; the next two deltas
        # (520-500, 530-520) are attributable to this bucket.
        assert row["volume"] == 30

    def test_rollover_persists_previous_and_tracks_volume_deltas(
        self, persisted
    ) -> None:
        agg = TickToCandleAggregator(on_candle=lambda *_: None)
        agg.handle_quote(_quote("100", 1000, 0))  # anchor counter
        agg.handle_quote(_quote("101", 1050, 0, second=30))  # +50 in minute 0
        agg.handle_quote(_quote("102", 1080, 1))  # rolls; +30 in minute 1

        assert len(persisted) == 1  # minute-0 bucket closed by rollover
        first = persisted[0]
        assert first["timestamp"] == datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)
        assert first["volume"] == 50

        assert agg.in_flight == 1
        agg.flush()
        second = persisted[1]
        assert second["timestamp"] == datetime(2026, 8, 22, 9, 1, tzinfo=timezone.utc)
        assert second["close"] == Decimal("102")
        assert second["volume"] == 30

    def test_volume_decrease_is_ignored_not_negative(self, persisted) -> None:
        agg = TickToCandleAggregator(on_candle=lambda *_: None)
        agg.handle_quote(_quote("100", 1000, 0))
        agg.handle_quote(_quote("101", 900, 0, second=30))  # counter went backwards
        agg.flush()
        assert persisted[0]["volume"] == 0

    def test_bad_token_ignored(self, persisted) -> None:
        agg = TickToCandleAggregator()
        agg.handle_quote(_FakeQuote("unknown", "100", None, datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc)))
        agg.flush()
        assert persisted == []

    def test_on_candle_callback_invoked_with_token_and_timestamp(
        self, persisted
    ) -> None:
        seen: list[tuple[int, datetime]] = []
        agg = TickToCandleAggregator(on_candle=lambda tok, ts: seen.append((tok, ts)))
        agg.handle_quote(_quote("100", 10, 0))
        agg.flush()
        assert seen == [(123, datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc))]
