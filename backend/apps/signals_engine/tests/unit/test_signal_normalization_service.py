from __future__ import annotations

from typing import Any

import pytest

from apps.signals_engine.application.signal_normalization_service import (
    SignalNormalizationService,
)
from apps.signals_engine.domain.exceptions import InvalidSignalPayloadError
from apps.signals_engine.domain.value_objects import SignalDirection


class TestSignalNormalizationService:
    @pytest.fixture
    def service(self) -> SignalNormalizationService:
        return SignalNormalizationService()

    def test_normalize_tradingview_alert(self, service: SignalNormalizationService) -> None:
        payload: dict[str, Any] = {
            "ticker": "RELIANCE",
            "close": 2850.50,
            "direction": "BUY",
            "timeframe": "1h",
            "confidence_hint": 0.75,
            "indicator_snapshot": {"rsi_14": 62.5},
            "alert_id": "tv_001",
        }
        signal = service.normalize(payload, "tradingview", "tv_001")
        assert signal.symbol == "RELIANCE"
        assert signal.direction == SignalDirection.BUY
        assert signal.timeframe == "1h"
        assert signal.confidence_hint == 0.75
        assert signal.indicator_snapshot == {"rsi_14": 62.5}
        assert signal.source_alert_id == "tv_001"

    def test_normalize_with_symbol_field(self, service: SignalNormalizationService) -> None:
        payload: dict[str, Any] = {
            "symbol": "TCS",
            "close": 3500.00,
            "action": "SELL",
            "interval": "4h",
            "alert_id": "tv_002",
        }
        signal = service.normalize(payload, "tradingview", "tv_002")
        assert signal.symbol == "TCS"
        assert signal.direction == SignalDirection.SELL
        assert signal.timeframe == "4h"

    def test_normalize_missing_ticker_raises_error(self, service: SignalNormalizationService) -> None:
        with pytest.raises(InvalidSignalPayloadError, match="Missing ticker"):
            service.normalize({}, "tradingview", "tv_003")

    def test_normalize_default_direction_is_wait(self, service: SignalNormalizationService) -> None:
        payload: dict[str, Any] = {
            "ticker": "HDFC",
            "close": 1600.00,
            "alert_id": "tv_004",
        }
        signal = service.normalize(payload, "tradingview", "tv_004")
        assert signal.direction == SignalDirection.WAIT

    def test_normalize_indicator_snapshot_defaults_to_empty(self, service: SignalNormalizationService) -> None:
        payload: dict[str, Any] = {
            "ticker": "SBIN",
            "close": 800.00,
            "alert_id": "tv_005",
        }
        signal = service.normalize(payload, "tradingview", "tv_005")
        assert signal.indicator_snapshot == {}

    def test_normalize_account_id_preserved(self, service: SignalNormalizationService) -> None:
        import uuid
        account_id = uuid.uuid4()
        payload: dict[str, Any] = {
            "ticker": "AXIS",
            "close": 1000.00,
            "alert_id": "tv_006",
        }
        signal = service.normalize(payload, "tradingview", "tv_006", account_id=account_id)
        assert signal.account_id == account_id

    def test_normalize_buy_variants(self, service: SignalNormalizationService) -> None:
        for variant in ("BUY", "LONG", "BULLISH"):
            payload: dict[str, Any] = {
                "ticker": "TEST",
                "close": 100.00,
                "direction": variant,
                "alert_id": f"tv_{variant}",
            }
            signal = service.normalize(payload, "tradingview", f"tv_{variant}")
            assert signal.direction == SignalDirection.BUY, f"Failed for {variant}"

    def test_normalize_sell_variants(self, service: SignalNormalizationService) -> None:
        for variant in ("SELL", "SHORT", "BEARISH"):
            payload: dict[str, Any] = {
                "ticker": "TEST",
                "close": 100.00,
                "direction": variant,
                "alert_id": f"tv_{variant}",
            }
            signal = service.normalize(payload, "tradingview", f"tv_{variant}")
            assert signal.direction == SignalDirection.SELL, f"Failed for {variant}"
