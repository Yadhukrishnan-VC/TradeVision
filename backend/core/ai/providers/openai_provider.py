"""
TradeVision AI — OpenAI provider stub.

Phase 0: All lifecycle methods raise NotImplementedError.
Will be fully implemented when OpenAI is designated as the active provider.

To activate: set AI_PROVIDER=openai and OPENAI_API_KEY in your environment,
then implement this class following the GeminiProvider as a reference.
"""

import logging
from typing import Any, ClassVar

from core.ai.base_provider import AIRawResponse, AIRequest, BaseAIProvider
from core.ai.exceptions import AIProviderError

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseAIProvider):
    """
    OpenAI GPT provider — Phase 0 stub.

    All methods raise ``NotImplementedError``. The class exists to satisfy
    the factory's provider map and to act as a typed extension point.
    """

    provider_name: ClassVar[str] = "openai"

    def validate_connection(self) -> bool:
        """Not implemented in Phase 0."""
        raise NotImplementedError(
            "OpenAIProvider.validate_connection() is not implemented in Phase 0. "
            "Implement this method when configuring AI_PROVIDER=openai."
        )

    def health_check(self) -> dict[str, Any]:
        """Not implemented in Phase 0."""
        raise NotImplementedError(
            "OpenAIProvider.health_check() is not implemented in Phase 0. "
            "Implement this method when configuring AI_PROVIDER=openai."
        )

    def complete(self, request: AIRequest) -> AIRawResponse:
        """Not implemented in Phase 0."""
        raise NotImplementedError(
            "OpenAIProvider.complete() is not implemented in Phase 0. "
            "Implement this method when configuring AI_PROVIDER=openai."
        )

    def close(self) -> None:
        """No resources to release for this stub provider."""
        logger.debug(
            "openai_stub_provider_close_called",
            extra={"provider": self.provider_name},
        )
