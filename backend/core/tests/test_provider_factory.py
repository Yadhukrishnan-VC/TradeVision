"""
Tests for AIProviderFactory — singleton, reset, unknown provider handling.
"""

import pytest

from core.ai.provider_factory import AIProviderFactory
from core.ai.exceptions import AIProviderError


class TestAIProviderFactory:
    """Test singleton behavior and provider resolution."""

    def setup_method(self) -> None:
        AIProviderFactory.reset()

    def teardown_method(self) -> None:
        AIProviderFactory.reset()

    def test_returns_same_instance(self) -> None:
        p1 = AIProviderFactory.get_provider()
        p2 = AIProviderFactory.get_provider()
        assert p1 is p2

    def test_reset_clears_instance(self) -> None:
        p1 = AIProviderFactory.get_provider()
        AIProviderFactory.reset()
        p2 = AIProviderFactory.get_provider()
        assert p1 is not p2

    def test_returns_provider_with_name(self) -> None:
        provider = AIProviderFactory.get_provider()
        assert hasattr(provider, "provider_name")
        assert isinstance(provider.provider_name, str)
