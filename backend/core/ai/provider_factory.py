"""
TradeVision AI — AI provider factory.

Implements the singleton pattern for AI provider instances. The active
provider is determined by ``TradeVisionConfig.ai_provider`` (which reads
``settings.AI_PROVIDER``) and created exactly once per process.

Thread-safe double-checked locking prevents multiple instantiations under
concurrent request load.

Usage::

    from core.ai.provider_factory import AIProviderFactory

    provider = AIProviderFactory.get_provider()
    ok = provider.validate_connection()
"""

import logging
import threading
from typing import ClassVar

from core.ai.base_provider import BaseAIProvider
from core.ai.exceptions import AIAuthenticationError, AIProviderError

logger = logging.getLogger(__name__)


class AIProviderFactory:
    """
    Singleton factory for AI provider instances.

    Only one provider instance exists per process. Calling ``get_provider()``
    multiple times returns the same object. Call ``reset()`` to destroy the
    current instance and force re-creation on the next call — used for test
    isolation and provider switching.

    Provider selection is driven by ``TradeVisionConfig.ai_provider``.
    The factory reads the config at first call, not at import time, so
    settings overrides in tests take effect correctly.
    """

    _instance: ClassVar[BaseAIProvider | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_provider(cls) -> BaseAIProvider:
        """
        Return the active AI provider singleton.

        Creates the provider on first call using the configuration in
        ``TradeVisionConfig``. Thread-safe via double-checked locking.

        Returns:
            The configured ``BaseAIProvider`` instance.

        Raises:
            AIProviderError:       If the configured provider name is unknown.
            AIAuthenticationError: If the provider cannot authenticate with
                                   the supplied credentials.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls._create_provider()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """
        Destroy the current singleton and release its resources.

        The next call to ``get_provider()`` will create a fresh instance.
        Intended for test isolation and graceful provider switching.
        """
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.close()
                except NotImplementedError:
                    logger.debug(
                        "provider_close_not_implemented_during_reset",
                        extra={"provider": cls._instance.provider_name},
                    )
                except Exception as exc:
                    logger.warning(
                        "provider_close_error_during_reset",
                        extra={"error": str(exc)},
                    )
            cls._instance = None
            logger.debug("ai_provider_factory_reset")

    @classmethod
    def _create_provider(cls) -> BaseAIProvider:
        """
        Instantiate and return the correct provider for the current configuration.

        Imports are deferred to this method to avoid circular imports at
        module load time.

        Returns:
            A freshly instantiated ``BaseAIProvider``.

        Raises:
            AIProviderError:       If the provider name is not recognised.
            AIAuthenticationError: If provider credentials are missing or invalid.
        """
        from core.ai.providers.claude_provider import ClaudeProvider
        from core.ai.providers.gemini_provider import GeminiProvider
        from core.ai.providers.ollama_provider import OllamaProvider
        from core.ai.providers.openai_provider import OpenAIProvider
        from core.config import config

        provider_name: str = config.ai_provider.lower()

        provider_map: dict[str, type[BaseAIProvider]] = {
            "gemini": GeminiProvider,
            "openai": OpenAIProvider,
            "claude": ClaudeProvider,
            "ollama": OllamaProvider,
        }

        if provider_name not in provider_map:
            raise AIProviderError(
                f"Unknown AI provider: '{provider_name}'. "
                f"Supported providers: {sorted(provider_map.keys())}. "
                "Update settings.AI_PROVIDER to a supported value."
            )

        logger.info(
            "ai_provider_creating",
            extra={"provider": provider_name},
        )

        if provider_name == "gemini":
            if not config.gemini_api_key:
                raise AIAuthenticationError(
                    "GEMINI_API_KEY is not set. "
                    "Configure it in your .env file before starting the application."
                )
            instance: BaseAIProvider = GeminiProvider(
                api_key=config.gemini_api_key,
                model_name=config.gemini_model,
            )
        elif provider_name == "openai":
            instance = OpenAIProvider()
        elif provider_name == "claude":
            instance = ClaudeProvider()
        else:
            instance = OllamaProvider()

        logger.info(
            "ai_provider_created",
            extra={"provider": provider_name, "class": type(instance).__name__},
        )
        return instance
