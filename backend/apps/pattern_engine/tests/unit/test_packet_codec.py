from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from apps.pattern_engine.infrastructure.packet_codec import deserialize_packet
from core.events.event_types import (
    CircuitStatus,
    MarketTrend,
)


class TestDeserializePacket:
    def _packet_data(self) -> dict:
        return {
            "symbol": "RELIANCE",
            "timestamp": "2024-03-17T10:00:00+00:00",
            "freshness_validated": True,
            "price_context": {
                "current_price": "2500.5",
                "open_price": "2480.0",
                "high": "2510.0",
                "low": "2470.0",
                "volume": "1200000",
                "avg_volume_20d": "900000",
                "circuit_status": "NORMAL",
                "prev_close": "2450.0",
                "change_pct": "2.06",
            },
            "technical_context": {
                "trend": "UPTREND",
                "rsi_14": "61.5",
                "macd_histogram": "0.8",
                "bb_upper": "2600.0",
                "bb_lower": "2400.0",
            },
            "breadth_context": {
                "sector_index_change_pct": "0.4",
                "sector_advance_decline": "1.3",
                "nifty_change_pct": "0.2",
                "sensex_change_pct": "0.1",
            },
            "options_context": {
                "pcr": "1.05",
                "max_pain": "2490",
                "atm_iv": "13.5",
                "oi_change_pct": "4.2",
            },
            "global_context": {
                "dow_futures_pct": "0.1",
                "sgx_nifty_pct": "0.05",
                "crude_oil_pct": "-0.6",
                "usd_inr_change_pct": "0.02",
                "vix": "12",
                "india_vix": "11.5",
                "fii_net_flow_cr": "300",
            },
        }

    def test_full_packet(self) -> None:
        packet = deserialize_packet(self._packet_data())
        assert packet.symbol == "RELIANCE"
        assert packet.freshness_validated is True
        assert packet.timestamp == datetime(2024, 3, 17, 10, 0, tzinfo=timezone.utc)
        assert packet.price_context.current_price == Decimal("2500.5")
        assert packet.price_context.circuit_status == CircuitStatus.NORMAL
        assert packet.technical_context.trend == MarketTrend.UPTREND
        assert packet.technical_context.rsi_14 == Decimal("61.5")
        assert packet.breadth_context.nifty_change_pct == Decimal("0.2")
        assert packet.options_context is not None
        assert packet.options_context.pcr == Decimal("1.05")
        assert packet.global_context is not None
        assert packet.global_context.crude_oil_pct == Decimal("-0.6")

    def test_missing_optional_blocks_become_none(self) -> None:
        data = self._packet_data()
        data.pop("options_context")
        data.pop("global_context")
        packet = deserialize_packet(data)
        assert packet.options_context is None
        assert packet.global_context is None

    def test_missing_fields_default_tolerantly(self) -> None:
        data = self._packet_data()
        data["price_context"] = {}
        data["technical_context"] = {}
        packet = deserialize_packet(data)
        assert packet.price_context.current_price == Decimal(0)
        assert packet.price_context.circuit_status == CircuitStatus.NORMAL
        assert packet.technical_context.trend == MarketTrend.SIDEWAYS

    def test_naive_timestamp_gets_utc(self) -> None:
        data = self._packet_data()
        data["timestamp"] = "2024-03-17T10:00:00"
        packet = deserialize_packet(data)
        assert packet.timestamp.tzinfo is not None
        assert packet.timestamp == datetime(2024, 3, 17, 10, 0, tzinfo=timezone.utc)
