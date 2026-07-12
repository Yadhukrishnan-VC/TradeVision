"""
TradeVision AI — Ollama provider stub.

Typed stub — all four lifecycle methods raise ``NotImplementedError``.
Will be fully implemented in a future phase for local LLM inference.
"""

from typing import Any

from core.ai.base_provider import AIRequest, AIRawResponse, BaseAIProvider


class OllamaProvider(BaseAIProvider):
    """Ollama local LLM provider stub — not yet implemented."""

    provider_name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2") -> None:
        self._base_url = base_url
        self._model = model

    def validate_connection(self) -> bool:
        """Not implemented."""
        raise NotImplementedError("OllamaProvider.validate_connection() is not implemented.")

    def health_check(self) -> dict[str, Any]:
        """Not implemented."""
        raise NotImplementedError("OllamaProvider.health_check() is not implemented.")

    def complete(self, request: AIRequest) -> AIRawResponse:
        """Not implemented."""
        raise NotImplementedError("OllamaProvider.complete() is not implemented.")

    def close(self) -> None:
        """Not implemented."""
        raise NotImplementedError("OllamaProvider.close() is not implemented.")
