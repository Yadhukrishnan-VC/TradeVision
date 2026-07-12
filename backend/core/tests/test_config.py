"""
Tests for core.config — typed attribute access, defaults.
"""

import pytest
from django.test import override_settings

from core.config import TradeVisionConfig


class TestTradeVisionConfig:

    def test_reads_ai_provider(self) -> None:
        cfg = TradeVisionConfig()
        assert cfg.ai_provider == "gemini"

    def test_reads_gemini_model(self) -> None:
        cfg = TradeVisionConfig()
        assert cfg.gemini_model == "gemini-1.5-pro"

    def test_reads_market_data_provider(self) -> None:
        cfg = TradeVisionConfig()
        assert cfg.market_data_provider == "mock"

    def test_config_singleton_type(self) -> None:
        from core.config import config
        assert isinstance(config, TradeVisionConfig)

    def test_ai_confidence_floor_default(self) -> None:
        cfg = TradeVisionConfig()
        assert cfg.ai_confidence_floor == 0.55

    def test_ai_daily_budget_default(self) -> None:
        cfg = TradeVisionConfig()
        assert cfg.ai_daily_budget_usd == 10.0
