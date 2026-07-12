"""
TradeVision AI — Anthropic Claude provider stub.

Typed stub — all four lifecycle methods raise ``NotImplementedError``.
Will be fully implemented in a future phase when Claude is supported.
"""

from typing import Any

from core.ai.base_provider import AIRequest, AIRawResponse, BaseAIProvider


class ClaudeProvider(BaseAIProvider):
    """Anthropic Claude provider stub — not yet implemented."""

    provider_name = "claude"

    def __init__(self, api_key: str = "", model: str = "claude-3-5-sonnet-20241022") -> None:
        self._api_key = api_key
        self._model = model

    def validate_connection(self) -> bool:
        """Not implemented."""
        raise NotImplementedError("ClaudeProvider.validate_connection() is not implemented.")

    def health_check(self) -> dict[str, Any]:
        """Not implemented."""
        raise NotImplementedError("ClaudeProvider.health_check() is not implemented.")

    def complete(self, request: AIRequest) -> AIRawResponse:
        """Not implemented."""
        raise NotImplementedError("ClaudeProvider.complete() is not implemented.")

    def close(self) -> None:
        """Not implemented."""
        raise NotImplementedError("ClaudeProvider.close() is not implemented.")
