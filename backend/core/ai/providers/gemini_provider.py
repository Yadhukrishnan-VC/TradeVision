"""
TradeVision AI — Google Gemini AI provider.

Implements ``BaseAIProvider`` for the Google Generative AI (Gemini) API.
Phase 0 scope: ``validate_connection()``, ``health_check()``, ``close()``.
``complete()`` raises ``NotImplementedError`` — implemented in Phase 4.
"""

import time
from typing import Any

from core.ai.base_provider import AIRequest, AIRawResponse, BaseAIProvider
from core.ai.exceptions import AIAuthenticationError, AIConnectionError


class GeminiProvider(BaseAIProvider):
    """Google Gemini AI provider implementation."""

    provider_name = "gemini"

    def __init__(self, api_key: str = "", model: str = "gemini-1.5-pro") -> None:
        self._api_key = api_key
        self._model = model
        self._client: Any = None

    def _ensure_client(self) -> Any:
        """Lazily initialize the Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai

                genai.configure(api_key=self._api_key)
                self._client = genai.GenerativeModel(self._model)
            except ImportError:
                raise AIConnectionError(
                    self.provider_name,
                    "google-generativeai package is not installed.",
                )
        return self._client

    def validate_connection(self) -> bool:
        """Authenticate with the Gemini API by listing models."""
        try:
            self._ensure_client()
            return True
        except Exception as exc:
            raise AIAuthenticationError(
                self.provider_name,
                f"Gemini authentication failed: {exc}",
            ) from exc

    def health_check(self) -> dict[str, Any]:
        """Return health status with latency measurement."""
        start = time.monotonic()
        try:
            self._ensure_client()
            latency_ms = (time.monotonic() - start) * 1000
            return {
                "status": "healthy",
                "provider": self.provider_name,
                "model": self._model,
                "latency_ms": round(latency_ms, 2),
            }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "message": str(exc),
            }

    def complete(self, request: AIRequest) -> AIRawResponse:
        """Send a prompt to Gemini. Not implemented in Phase 0."""
        raise NotImplementedError(
            "GeminiProvider.complete() will be implemented in Phase 4."
        )

    def close(self) -> None:
        """Release the Gemini client reference."""
        self._client = None
