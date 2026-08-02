"""
Tests for TradeVisionConfig Zerodha credential accessors.
"""

from django.test import override_settings

from core.config import TradeVisionConfig


class TestZerodhaConfig:
    def test_defaults_empty(self) -> None:
        cfg = TradeVisionConfig()
        assert cfg.zerodha_api_key == ""
        assert cfg.zerodha_access_token == ""

    def test_reflects_override_settings(self) -> None:
        cfg = TradeVisionConfig()
        with override_settings(
            ZERODHA_API_KEY="kite-api-key",
            ZERODHA_ACCESS_TOKEN="kite-access-token",
        ):
            assert cfg.zerodha_api_key == "kite-api-key"
            assert cfg.zerodha_access_token == "kite-access-token"
