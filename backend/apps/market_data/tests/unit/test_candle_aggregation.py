from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from apps.market_data.application.candle_aggregation_service import (
    CandleAggregationService,
)
from apps.market_data.domain.entities import Candle
from apps.market_data.domain.value_objects import Timeframe
from core.market_data.base_provider import OHLCVBar

_IST = ZoneInfo("Asia/Kolkata")
_UTC = ZoneInfo("UTC")


def _make_bar(
    minute_offset: int,
    open_p: Decimal = Decimal("100"),
    high: Decimal = Decimal("105"),
    low: Decimal = Decimal("95"),
    close: Decimal = Decimal("102"),
    volume: int = 10000,
    base_time: datetime | None = None,
) -> OHLCVBar:
    base = base_time or datetime(2025, 3, 10, 9, 15, tzinfo=_IST)
    ts = base + timedelta(minutes=minute_offset)
    return OHLCVBar(
        timestamp=ts,
        open_price=open_p,
        high=high,
        low=low,
        close_price=close,
        volume=volume,
    )


class TestCandleAggregationService:
    def test_passthrough_minute_1(self) -> None:
        service = CandleAggregationService()
        bars = [_make_bar(i) for i in range(5)]
        candles = service.aggregate(
            instrument_token=1001,
            base_candles=bars,
            target_timeframe=Timeframe.MINUTE_1,
        )
        assert len(candles) == 5
        for c in candles:
            assert c.timeframe == "1min"

    def test_15min_aggregation_aligned_to_0915(self) -> None:
        service = CandleAggregationService()
        bars = [
            _make_bar(0, open_p=Decimal("100"), close=Decimal("101")),
            _make_bar(1, open_p=Decimal("101"), close=Decimal("102")),
            _make_bar(14, open_p=Decimal("102"), close=Decimal("103")),
        ]
        candles = service.aggregate(
            instrument_token=1001,
            base_candles=bars,
            target_timeframe=Timeframe.MINUTE_15,
        )
        assert len(candles) == 1
        c = candles[0]
        assert c.timeframe == "15min"
        assert c.open == Decimal("100")
        assert c.close == Decimal("103")

    def test_15min_bucket_boundary(self) -> None:
        """15-min buckets are 09:15, 09:30, 09:45, ... not 09:00, 09:15."""
        service = CandleAggregationService()
        bars = [
            _make_bar(0, open_p=Decimal("100"), close=Decimal("101")),
            _make_bar(1, open_p=Decimal("101"), close=Decimal("102")),
            _make_bar(15, open_p=Decimal("200"), close=Decimal("201")),
            _make_bar(16, open_p=Decimal("201"), close=Decimal("202")),
        ]
        candles = service.aggregate(
            instrument_token=1001,
            base_candles=bars,
            target_timeframe=Timeframe.MINUTE_15,
        )
        assert len(candles) == 2
        assert candles[0].close == Decimal("102")
        assert candles[1].close == Decimal("202")
        assert candles[1].open == Decimal("200")

    def test_30min_aggregation(self) -> None:
        service = CandleAggregationService()
        bars = [
            _make_bar(0, open_p=Decimal("100")),
            _make_bar(15, open_p=Decimal("110")),
            _make_bar(30, open_p=Decimal("120")),
        ]
        candles = service.aggregate(
            instrument_token=1001,
            base_candles=bars,
            target_timeframe=Timeframe.MINUTE_30,
        )
        assert len(candles) == 2
        assert candles[0].open == Decimal("100")
        assert candles[1].open == Decimal("120")

    def test_empty_bars_raises(self) -> None:
        service = CandleAggregationService()
        with pytest.raises(ValueError, match="Cannot merge empty"):
            service.aggregate(
                instrument_token=1001,
                base_candles=[],
                target_timeframe=Timeframe.MINUTE_15,
            )

    def test_high_low_calculation(self) -> None:
        service = CandleAggregationService()
        bars = [
            _make_bar(0, low=Decimal("90"), high=Decimal("110")),
            _make_bar(1, low=Decimal("95"), high=Decimal("120")),
            _make_bar(2, low=Decimal("85"), high=Decimal("105")),
        ]
        candles = service.aggregate(
            instrument_token=1001,
            base_candles=bars,
            target_timeframe=Timeframe.MINUTE_15,
        )
        assert len(candles) == 1
        assert candles[0].high == Decimal("120")
        assert candles[0].low == Decimal("85")

    def test_volume_sum(self) -> None:
        service = CandleAggregationService()
        bars = [
            _make_bar(0, volume=1000),
            _make_bar(1, volume=2000),
            _make_bar(2, volume=3000),
        ]
        candles = service.aggregate(
            instrument_token=1001,
            base_candles=bars,
            target_timeframe=Timeframe.MINUTE_15,
        )
        assert candles[0].volume == 6000

    def test_weekly_timeframe_unsupported(self) -> None:
        service = CandleAggregationService()
        with pytest.raises(Exception):
            service.aggregate(
                instrument_token=1001,
                base_candles=[_make_bar(0)],
                target_timeframe=Timeframe.WEEK_1,
            )
