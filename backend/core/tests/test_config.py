"""
Tests for core.config — typed attribute access, defaults.
"""

import pytest
from django.test import override_settings

from core.config import TradeVisionConfig


class TestTradeVisionConfig:

    def test_reads_django_settings(self) -> None:
        cfg = TradeVisionConfig()
        assert cfg.DEBUG is not None  # Should read from Django settings

    def test_unknown_attribute_raises(self) -> None:
        cfg = TradeVisionConfig()
        with pytest.raises(AttributeError):
            _ = cfg.NONEXISTENT_SETTING_XYZ

    def test_config_singleton_type(self) -> None:
        from core.config import config
        assert isinstance(config, TradeVisionConfig)
