"""
Tests for AIProviderFactory singleton, selection, and reset.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from core.ai.base_provider import BaseAIProvider
from core.ai.exceptions import AIAuthenticationError, AIProviderError
from core.ai.provider_factory import AIProviderFactory


@pytest.fixture(autouse=True)
def reset_ai_factory() -> None:
    """Reset the factory singleton before and after every test in this module."""
    AIProviderFactory.reset()
    yield
    AIProviderFactory.reset()


@pytest.fixture
def mock_genai():
    """Mock the google.generativeai SDK globally for tests that instantiate Gemini."""
    mock = MagicMock()
    mock.list_models.return_value = ["gemini-1.5-pro"]
    mock.GenerativeModel.return_value = MagicMock()
    google_mock = MagicMock()
    google_mock.generativeai = mock
    with patch.dict(sys.modules, {"google": google_mock, "google.generativeai": mock}):
        yield mock


@pytest.fixture
def gemini_config():
    """Patch core.config.config to provide Gemini credentials."""
    with patch("core.config.config") as mock_cfg:
        mock_cfg.ai_provider = "gemini"
        mock_cfg.gemini_api_key = "test-api-key-abc123"
        mock_cfg.gemini_model = "gemini-1.5-pro"
        yield mock_cfg


class TestAIProviderFactorySingleton:
    """Factory must return the same instance on repeated calls."""

    def test_get_provider_returns_base_provider(
        self, mock_genai: MagicMock, gemini_config: MagicMock
    ) -> None:
        provider = AIProviderFactory.get_provider()
        assert isinstance(provider, BaseAIProvider)

    def test_singleton_same_instance(
        self, mock_genai: MagicMock, gemini_config: MagicMock
    ) -> None:
        first = AIProviderFactory.get_provider()
        second = AIProviderFactory.get_provider()
        assert first is second

    def test_get_provider_never_returns_none(
        self, mock_genai: MagicMock, gemini_config: MagicMock
    ) -> None:
        provider = AIProviderFactory.get_provider()
        assert provider is not None

    def test_reset_allows_new_instance(
        self, mock_genai: MagicMock, gemini_config: MagicMock
    ) -> None:
        first = AIProviderFactory.get_provider()
        AIProviderFactory.reset()
        second = AIProviderFactory.get_provider()
        assert first is not second

    def test_double_reset_does_not_raise(self) -> None:
        AIProviderFactory.reset()
        AIProviderFactory.reset()


class TestAIProviderFactorySelection:
    """Factory must select the correct provider class from configuration."""

    def test_gemini_provider_selected(
        self, mock_genai: MagicMock, gemini_config: MagicMock
    ) -> None:
        from core.ai.providers.gemini_provider import GeminiProvider
        provider = AIProviderFactory.get_provider()
        assert isinstance(provider, GeminiProvider)

    def test_openai_provider_selected(self) -> None:
        with patch("core.config.config") as mock_cfg:
            mock_cfg.ai_provider = "openai"
            from core.ai.providers.openai_provider import OpenAIProvider
            provider = AIProviderFactory.get_provider()
            assert isinstance(provider, OpenAIProvider)

    def test_claude_provider_selected(self) -> None:
        with patch("core.config.config") as mock_cfg:
            mock_cfg.ai_provider = "claude"
            from core.ai.providers.claude_provider import ClaudeProvider
            provider = AIProviderFactory.get_provider()
            assert isinstance(provider, ClaudeProvider)

    def test_ollama_provider_selected(self) -> None:
        with patch("core.config.config") as mock_cfg:
            mock_cfg.ai_provider = "ollama"
            from core.ai.providers.ollama_provider import OllamaProvider
            provider = AIProviderFactory.get_provider()
            assert isinstance(provider, OllamaProvider)

    def test_unknown_provider_raises_ai_provider_error(self) -> None:
        with patch("core.config.config") as mock_cfg:
            mock_cfg.ai_provider = "nonexistent_provider_xyz"
            with pytest.raises(AIProviderError):
                AIProviderFactory.get_provider()

    def test_unknown_provider_error_message_contains_name(self) -> None:
        bad_name = "totally_fake_provider"
        with patch("core.config.config") as mock_cfg:
            mock_cfg.ai_provider = bad_name
            with pytest.raises(AIProviderError) as exc_info:
                AIProviderFactory.get_provider()
            assert bad_name in str(exc_info.value)

    def test_missing_gemini_api_key_raises_authentication_error(
        self, mock_genai: MagicMock
    ) -> None:
        with patch("core.config.config") as mock_cfg:
            mock_cfg.ai_provider = "gemini"
            mock_cfg.gemini_api_key = ""
            mock_cfg.gemini_model = "gemini-1.5-pro"
            with pytest.raises(AIAuthenticationError):
                AIProviderFactory.get_provider()

    def test_provider_name_attribute_matches_config(
        self, mock_genai: MagicMock, gemini_config: MagicMock
    ) -> None:
        provider = AIProviderFactory.get_provider()
        assert provider.provider_name == "gemini"
