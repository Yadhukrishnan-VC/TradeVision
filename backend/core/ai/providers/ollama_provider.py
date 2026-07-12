"""
TradeVision AI — Ollama local LLM provider stub.

Phase 0: All lifecycle methods raise NotImplementedError.
Will be fully implemented when Ollama is designated as the active provider.

To activate: set AI_PROVIDER=ollama and OLLAMA_BASE_URL in your environment,
then implement this class following the GeminiProvider as a reference.
Ollama requires a locally running Ollama server.
"""

import logging
from typing import Any, ClassVar

from core.ai.base_provider import AIRawResponse, AIRequest, BaseAIProvider

logger = logging.getLogger(__name__)


class OllamaProvider(BaseAIProvider):
    """
    Ollama local LLM provider — Phase 0 stub.

    All methods raise ``NotImplementedError``. The class exists to satisfy
    the factory's provider map and to act as a typed extension point.
    Ollama enables self-hosted inference without external API calls.
    """

    provider_name: ClassVar[str] = "ollama"

    def validate_connection(self) -> bool:
        """Not implemented in Phase 0."""
        raise NotImplementedError(
            "OllamaProvider.validate_connection() is not implemented in Phase 0. "
            "Implement this method when configuring AI_PROVIDER=ollama."
        )

    def health_check(self) -> dict[str, Any]:
        """Not implemented in Phase 0."""
        raise NotImplementedError(
            "OllamaProvider.health_check() is not implemented in Phase 0. "
            "Implement this method when configuring AI_PROVIDER=ollama."
        )

    def complete(self, request: AIRequest) -> AIRawResponse:
        """Not implemented in Phase 0."""
        raise NotImplementedError(
            "OllamaProvider.complete() is not implemented in Phase 0. "
            "Implement this method when configuring AI_PROVIDER=ollama."
        )

    def close(self) -> None:
        """No resources to release for this stub provider."""
        logger.debug(
            "ollama_stub_provider_close_called",
            extra={"provider": self.provider_name},
        )
