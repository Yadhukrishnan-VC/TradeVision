from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from django.test import TestCase

from apps.market_data.application.candle_aggregation_service import (
    CandleAggregationService,
)
from apps.market_data.domain.value_objects import Timeframe
from core.market_data.base_provider import OHLCVBar


class TestCandleAggregationSessionAlignment(TestCase):
    """Integration tests verifying session-aligned candle bucketing."""

    def setUp(self) -> None:
        self.service = CandleAggregationService()

    def test_session_aligned_15min_buckets(self) -> None:
        """Verify that 15-min buckets are anchored to 09:15 IST."""
        from zoneinfo import ZoneInfo

        _IST = ZoneInfo("Asia/Kolkata")
        base = datetime(2025, 3, 10, 9, 15, tzinfo=_IST)

        bars: list[OHLCVBar] = []
        for i in range(60):
            bars.append(OHLCVBar(
                timestamp=base + __import__("datetime").timedelta(minutes=i),
                open_price=Decimal("100") + Decimal(i),
                high=Decimal("105") + Decimal(i),
                low=Decimal("95") + Decimal(i),
                close_price=Decimal("102") + Decimal(i),
                volume=10000 + (i * 100),
            ))

        candles = self.service.aggregate(
            instrument_token=1001,
            base_candles=bars,
            target_timeframe=Timeframe.MINUTE_15,
        )

        self.assertEqual(len(candles), 4)
        self.assertEqual(candles[0].open, Decimal("100"))
        self.assertEqual(candles[0].close, Decimal("114"))

        self.assertEqual(candles[1].open, Decimal("115"))
        self.assertEqual(candles[1].close, Decimal("129"))

    def test_1min_passthrough_preserves_all_bars(self) -> None:
        bars = [
            OHLCVBar(
                timestamp=datetime(2025, 3, 10, 9, 15, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata")),
                open_price=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close_price=Decimal("103"),
                volume=10000,
            ),
            OHLCVBar(
                timestamp=datetime(2025, 3, 10, 9, 16, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Kolkata")),
                open_price=Decimal("103"),
                high=Decimal("108"),
                low=Decimal("102"),
                close_price=Decimal("107"),
                volume=15000,
            ),
        ]

        candles = self.service.aggregate(
            instrument_token=1001,
            base_candles=bars,
            target_timeframe=Timeframe.MINUTE_1,
        )

        self.assertEqual(len(candles), 2)
        for c in candles:
            self.assertEqual(c.timeframe, "1min")

    def test_5min_aggregation_alignment(self) -> None:
        from zoneinfo import ZoneInfo

        _IST = ZoneInfo("Asia/Kolkata")
        base = datetime(2025, 3, 10, 9, 15, tzinfo=_IST)

        bars = [
            OHLCVBar(timestamp=base, open_price=Decimal("100"), high=Decimal("101"), low=Decimal("99"), close_price=Decimal("100"), volume=1000),
            OHLCVBar(timestamp=base + __import__("datetime").timedelta(minutes=1), open_price=Decimal("100"), high=Decimal("102"), low=Decimal("99"), close_price=Decimal("101"), volume=2000),
            OHLCVBar(timestamp=base + __import__("datetime").timedelta(minutes=5), open_price=Decimal("105"), high=Decimal("106"), low=Decimal("104"), close_price=Decimal("105"), volume=3000),
        ]

        candles = self.service.aggregate(
            instrument_token=1001,
            base_candles=bars,
            target_timeframe=Timeframe.MINUTE_5,
        )

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0].open, Decimal("100"))
        self.assertEqual(candles[0].close, Decimal("101"))
        self.assertEqual(candles[1].open, Decimal("105"))
