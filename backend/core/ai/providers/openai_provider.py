"""
TradeVision AI — OpenAI provider stub.

Typed stub — all four lifecycle methods raise ``NotImplementedError``.
Will be fully implemented in a future phase when OpenAI is supported.
"""

from typing import Any

from core.ai.base_provider import AIRequest, AIRawResponse, BaseAIProvider


class OpenAIProvider(BaseAIProvider):
    """OpenAI provider stub — not yet implemented."""

    provider_name = "openai"

    def __init__(self, api_key: str = "", model: str = "gpt-4o") -> None:
        self._api_key = api_key
        self._model = model

    def validate_connection(self) -> bool:
        """Not implemented."""
        raise NotImplementedError("OpenAIProvider.validate_connection() is not implemented.")

    def health_check(self) -> dict[str, Any]:
        """Not implemented."""
        raise NotImplementedError("OpenAIProvider.health_check() is not implemented.")

    def complete(self, request: AIRequest) -> AIRawResponse:
        """Not implemented."""
        raise NotImplementedError("OpenAIProvider.complete() is not implemented.")

    def close(self) -> None:
        """Not implemented."""
        raise NotImplementedError("OpenAIProvider.close() is not implemented.")
