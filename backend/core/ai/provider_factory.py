"""
TradeVision AI — AI provider factory.

Singleton factory that creates and caches the active AI provider instance.
Uses ``TradeVisionConfig`` instead of ``django.conf.settings`` directly,
making provider code testable outside the Django process.
"""

from typing import Any

from core.ai.base_provider import BaseAIProvider
from core.ai.exceptions import AIProviderError
from core.config import config

# Provider class registry — maps provider name to class
_PROVIDER_REGISTRY: dict[str, type[BaseAIProvider]] = {}


def _load_providers() -> None:
    """Lazy-load provider classes to avoid import-time side effects."""
    if _PROVIDER_REGISTRY:
        return
    from core.ai.providers.gemini_provider import GeminiProvider
    from core.ai.providers.openai_provider import OpenAIProvider
    from core.ai.providers.claude_provider import ClaudeProvider
    from core.ai.providers.ollama_provider import OllamaProvider

    _PROVIDER_REGISTRY.update(
        {
            "gemini": GeminiProvider,
            "openai": OpenAIProvider,
            "claude": ClaudeProvider,
            "ollama": OllamaProvider,
        }
    )


class AIProviderFactory:
    """
    Singleton factory for creating and managing AI provider instances.

    The factory reads the active provider name from ``TradeVisionConfig``
    and lazily instantiates the corresponding provider class. The instance
    is cached for the lifetime of the process.

    Usage::

        provider = AIProviderFactory.get_provider()
        response = provider.complete(request)
    """

    _instance: BaseAIProvider | None = None
    _provider_name: str | None = None

    @classmethod
    def get_provider(cls) -> BaseAIProvider:
        """
        Return the active AI provider, creating it if necessary.

        Returns:
            The cached provider instance.

        Raises:
            AIProviderError: If the configured provider name is unknown.
        """
        provider_name = config.ai_provider

        if cls._instance is not None and cls._provider_name == provider_name:
            return cls._instance

        _load_providers()

        provider_cls = _PROVIDER_REGISTRY.get(provider_name)
        if provider_cls is None:
            raise AIProviderError(
                f"Unknown AI provider: '{provider_name}'. "
                f"Available: {', '.join(sorted(_PROVIDER_REGISTRY))}"
            )

        # Build kwargs based on provider
        kwargs: dict[str, Any] = {"model": getattr(config, f"{provider_name}_model", "")}

        if provider_name == "gemini":
            kwargs["api_key"] = config.gemini_api_key
        elif provider_name == "openai":
            kwargs["api_key"] = config.openai_api_key
        elif provider_name == "claude":
            kwargs["api_key"] = config.anthropic_api_key
        elif provider_name == "ollama":
            kwargs["base_url"] = config.ollama_base_url

        cls._instance = provider_cls(**kwargs)  # type: ignore[arg-type]
        cls._provider_name = provider_name
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the factory — closes the current provider and clears cache.

        Intended for test teardown. After calling ``reset()``, the next
        call to ``get_provider()`` will create a fresh instance.
        """
        if cls._instance is not None:
            try:
                cls._instance.close()
            except Exception:
                pass
        cls._instance = None
        cls._provider_name = None
