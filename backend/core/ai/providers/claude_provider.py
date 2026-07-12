"""
TradeVision AI — Anthropic Claude provider stub.

Phase 0: All lifecycle methods raise NotImplementedError.
Will be fully implemented when Claude is designated as the active provider.

To activate: set AI_PROVIDER=claude and ANTHROPIC_API_KEY in your environment,
then implement this class following the GeminiProvider as a reference.
"""

import logging
from typing import Any, ClassVar

from core.ai.base_provider import AIRawResponse, AIRequest, BaseAIProvider

logger = logging.getLogger(__name__)


class ClaudeProvider(BaseAIProvider):
    """
    Anthropic Claude provider — Phase 0 stub.

    All methods raise ``NotImplementedError``. The class exists to satisfy
    the factory's provider map and to act as a typed extension point.
    """

    provider_name: ClassVar[str] = "claude"

    def validate_connection(self) -> bool:
        """Not implemented in Phase 0."""
        raise NotImplementedError(
            "ClaudeProvider.validate_connection() is not implemented in Phase 0. "
            "Implement this method when configuring AI_PROVIDER=claude."
        )

    def health_check(self) -> dict[str, Any]:
        """Not implemented in Phase 0."""
        raise NotImplementedError(
            "ClaudeProvider.health_check() is not implemented in Phase 0. "
            "Implement this method when configuring AI_PROVIDER=claude."
        )

    def complete(self, request: AIRequest) -> AIRawResponse:
        """Not implemented in Phase 0."""
        raise NotImplementedError(
            "ClaudeProvider.complete() is not implemented in Phase 0. "
            "Implement this method when configuring AI_PROVIDER=claude."
        )

    def close(self) -> None:
        """No resources to release for this stub provider."""
        logger.debug(
            "claude_stub_provider_close_called",
            extra={"provider": self.provider_name},
        )
