"""
Integration test: ``_build_packet`` session-facts enrichment.

Verifies that with a persisted instrument and candles, the Intelligence
packet assembly populates the session-fact fields (opening 15m candle,
previous-day H/L, 10-day average volume) that the deterministic setups need,
and that the previously-dropped payload fields (atr_14, bb_width,
support_levels, resistance_levels, supertrend) are mapped through.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.intelligence.infrastructure.ta_completed_handler import _build_packet
from apps.market_data.infrastructure.models import Candle, Instrument

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup_instrument_and_candles() -> None:
    Instrument.objects.create(
        instrument_token=1001,
        exchange="NSE",
        tradingsymbol="RELIANCE",
        name="Reliance Industries Ltd",
        segment="EQUITY",
        lot_size=1,
        tick_size=Decimal("0.05"),
        instrument_type="EQ",
    )
    # Previous trading day (Monday 2026-07-27): 15min opening candle + 1D candle.
    mon = datetime(2026, 7, 27, 3, 45, tzinfo=timezone.utc)  # 09:15 IST
    Candle.objects.create(
        instrument_id=1001, timeframe="1D", timestamp=mon,
        open=Decimal(90), high=Decimal(98), low=Decimal(88),
        close=Decimal(95), volume=1_000_000,
    )
    Candle.objects.create(
        instrument_id=1001, timeframe="15min", timestamp=mon,
        open=Decimal(90), high=Decimal(93), low=Decimal(89),
        close=Decimal(92), volume=200_000,
    )
    Candle.objects.create(
        instrument_id=1001, timeframe="15min",
        timestamp=mon + timedelta(minutes=15),
        open=Decimal(92), high=Decimal(95), low=Decimal(91),
        close=Decimal(94), volume=150_000,
    )
    # Reference session (Tuesday 2026-07-28): opening 15min candle.
    tue = datetime(2026, 7, 28, 3, 45, tzinfo=timezone.utc)  # 09:15 IST
    Candle.objects.create(
        instrument_id=1001, timeframe="15min", timestamp=tue,
        open=Decimal(100), high=Decimal(105), low=Decimal(99),
        close=Decimal(103), volume=1_000_000,
    )


def _payload() -> dict:
    return {
        "symbol": "RELIANCE",
        "snapshot_id": "snap-1",
        "exchange": "NSE",
        "timeframe": "1D",
        "snapshot_timestamp": "2026-07-28T10:00:00+00:00",
        "indicators": {
            "rsi_14": 62.5,
            "atr_14": "12.5",
            "bb_width": "0.08",
            "vwap": "3100.00",
            "ema_20": "3080.00",
            "supertrend_value": "3050.00",
            "supertrend_direction": "up",
            "support_levels": [3050.0, 3000.0],
            "resistance_levels": [3150.0, 3200.0],
        },
        "price": {
            "close": "3124.50",
            "open": "3100.00",
            "high": "3145.00",
            "low": "3090.00",
            "volume": 1200000,
            "avg_volume_20d": "400000",
        },
    }


class TestBuildPacketEnrichment:
    @override_settings(MARKET_EXCHANGE="NSE")
    def test_populates_session_facts_and_payload_fields(
        self, setup_instrument_and_candles
    ) -> None:
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        packet = _build_packet(_payload(), occurred_at)

        tech = packet.technical_context
        price = packet.price_context

        # Payload-mapped fields (previously dropped) now populate.
        assert tech.atr_14 == Decimal("12.5")
        assert tech.bb_width == Decimal("0.08")
        assert tech.supertrend_value == Decimal("3050.00")
        assert tech.supertrend_direction == "up"
        assert tech.support_levels == (Decimal("3050.0"), Decimal("3000.0"))
        assert tech.resistance_levels == (Decimal("3150.0"), Decimal("3200.0"))
        assert price.avg_volume_20d == 400_000

        # Session facts from persisted candles.
        assert tech.opening_15m_open == Decimal(100)
        assert tech.opening_15m_high == Decimal(105)
        assert tech.opening_15m_low == Decimal(99)
        assert tech.opening_15m_volume == 1_000_000
        assert tech.prev_day_high == Decimal(98)
        assert tech.prev_day_low == Decimal(88)
        assert price.avg_volume_10d == 1_000_000

    @override_settings(MARKET_EXCHANGE="NSE")
    def test_returns_packet_unchanged_when_instrument_missing(
        self,
    ) -> None:
        occurred_at = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        packet = _build_packet(_payload(), occurred_at)

        assert packet.technical_context.opening_15m_open is None
        assert packet.technical_context.prev_day_high is None
        assert packet.price_context.avg_volume_10d is None
        # Payload-mapped fields still populate even without session facts.
        assert packet.technical_context.atr_14 == Decimal("12.5")
        assert packet.technical_context.supertrend_direction == "up"
