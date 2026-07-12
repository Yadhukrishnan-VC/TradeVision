"""
Tests for AI provider interface compliance.

Verifies that all provider classes satisfy the ``BaseAIProvider`` contract:
validate_connection(), health_check(), close(), and complete() behavior.
"""

import pytest

from core.ai.base_provider import BaseAIProvider
from core.ai.providers.gemini_provider import GeminiProvider
from core.ai.providers.openai_provider import OpenAIProvider
from core.ai.providers.claude_provider import ClaudeProvider
from core.ai.providers.ollama_provider import OllamaProvider


class TestProviderInterfaceCompliance:
    """All provider classes must implement BaseAIProvider."""

    @pytest.mark.parametrize(
        "provider_cls",
        [GeminiProvider, OpenAIProvider, ClaudeProvider, OllamaProvider],
    )
    def test_is_subclass(self, provider_cls: type) -> None:
        assert issubclass(provider_cls, BaseAIProvider)

    @pytest.mark.parametrize(
        "provider_cls",
        [OpenAIProvider, ClaudeProvider, OllamaProvider],
    )
    def test_validate_connection_raises_not_implemented(self, provider_cls: type) -> None:
        provider = provider_cls(api_key="test")
        with pytest.raises(NotImplementedError):
            provider.validate_connection()

    @pytest.mark.parametrize(
        "provider_cls",
        [OpenAIProvider, ClaudeProvider, OllamaProvider],
    )
    def test_health_check_raises_not_implemented(self, provider_cls: type) -> None:
        provider = provider_cls(api_key="test")
        with pytest.raises(NotImplementedError):
            provider.health_check()

    @pytest.mark.parametrize(
        "provider_cls",
        [OpenAIProvider, ClaudeProvider, OllamaProvider],
    )
    def test_complete_raises_not_implemented(self, provider_cls: type) -> None:
        from core.ai.base_provider import AIRequest
        provider = provider_cls(api_key="test")
        request = AIRequest(event_type="test", symbol="TEST", prompt="test")
        with pytest.raises(NotImplementedError):
            provider.complete(request)

    @pytest.mark.parametrize(
        "provider_cls",
        [OpenAIProvider, ClaudeProvider, OllamaProvider],
    )
    def test_close_raises_not_implemented(self, provider_cls: type) -> None:
        provider = provider_cls(api_key="test")
        with pytest.raises(NotImplementedError):
            provider.close()

    def test_provider_name_attribute(self) -> None:
        assert GeminiProvider.provider_name == "gemini"
        assert OpenAIProvider.provider_name == "openai"
        assert ClaudeProvider.provider_name == "claude"
        assert OllamaProvider.provider_name == "ollama"
