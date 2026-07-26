from __future__ import annotations

from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase

from apps.market_data.infrastructure.models import Candle, Instrument


class TestInstrumentModel(TestCase):
    def test_create_instrument(self) -> None:
        instrument = Instrument.objects.create(
            instrument_token=1001,
            exchange="NSE",
            tradingsymbol="RELIANCE",
            name="Reliance Industries Ltd",
            segment="EQUITY",
            lot_size=1,
            tick_size=Decimal("0.05"),
            instrument_type="EQ",
        )
        self.assertEqual(str(instrument), "NSE:RELIANCE")
        self.assertTrue(instrument.is_active)

    def test_unique_exchange_symbol_constraint(self) -> None:
        Instrument.objects.create(
            instrument_token=1001,
            exchange="NSE",
            tradingsymbol="RELIANCE",
        )
        with self.assertRaises(IntegrityError):
            Instrument.objects.create(
                instrument_token=1002,
                exchange="NSE",
                tradingsymbol="RELIANCE",
            )

    def test_active_filter(self) -> None:
        Instrument.objects.create(
            instrument_token=1001,
            exchange="NSE",
            tradingsymbol="ACTIVE1",
            is_active=True,
        )
        Instrument.objects.create(
            instrument_token=1002,
            exchange="NSE",
            tradingsymbol="INACTIVE1",
            is_active=False,
        )

        active_count = Instrument.objects.filter(is_active=True).count()
        self.assertEqual(active_count, 1)


class TestCandleModel(TestCase):
    def setUp(self) -> None:
        self.instrument = Instrument.objects.create(
            instrument_token=1001,
            exchange="NSE",
            tradingsymbol="RELIANCE",
        )

    def test_create_candle(self) -> None:
        from datetime import datetime, timezone

        candle = Candle.objects.create(
            instrument=self.instrument,
            timeframe="15min",
            timestamp=datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("99"),
            close=Decimal("103"),
            volume=50000,
        )
        self.assertEqual(candle.timeframe, "15min")
        self.assertEqual(candle.volume, 50000)

    def test_unique_constraint(self) -> None:
        from datetime import datetime, timezone

        ts = datetime(2025, 3, 10, 9, 15, tzinfo=timezone.utc)

        Candle.objects.create(
            instrument=self.instrument,
            timeframe="15min",
            timestamp=ts,
            open=Decimal("100"),
            high=Decimal("105"),
            low=Decimal("99"),
            close=Decimal("103"),
            volume=50000,
        )
        with self.assertRaises(IntegrityError):
            Candle.objects.create(
                instrument=self.instrument,
                timeframe="15min",
                timestamp=ts,
                open=Decimal("200"),
                high=Decimal("205"),
                low=Decimal("199"),
                close=Decimal("203"),
                volume=60000,
            )
