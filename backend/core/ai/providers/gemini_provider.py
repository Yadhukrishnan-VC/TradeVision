"""
TradeVision AI — Gemini AI provider.

Phase 0 scope:
    ✓ SDK initialisation and authentication
    ✓ validate_connection() — verifies API key via list_models()
    ✓ health_check()        — returns latency and model availability
    ✓ close()               — releases client reference
    ✗ complete()            — raises NotImplementedError (implemented in Phase 4)

Phase 4 will add:
    - complete() with full prompt submission
    - Token counting and cost estimation
    - Retry logic with exponential backoff
    - Rate limit tracking via Redis
"""

import logging
import time
from typing import Any, ClassVar

from core.ai.base_provider import AIRawResponse, AIRequest, BaseAIProvider
from core.ai.exceptions import (
    AIAuthenticationError,
    AIConnectionError,
    AIProviderError,
)

logger = logging.getLogger(__name__)


class GeminiProvider(BaseAIProvider):
    """
    Google Gemini AI provider.

    Authenticates with the Gemini API using the provided API key and
    initialises a ``GenerativeModel`` client for the configured model.

    Args:
        api_key:    Google Gemini API key (from ``settings.GEMINI_API_KEY``).
        model_name: Gemini model identifier (e.g. ``"gemini-1.5-pro"``).
    """

    provider_name: ClassVar[str] = "gemini"

    def __init__(self, api_key: str, model_name: str) -> None:
        if not api_key:
            raise AIAuthenticationError(
                "Gemini API key must not be empty. "
                "Set GEMINI_API_KEY in your environment configuration."
            )
        self._api_key: str = api_key
        self._model_name: str = model_name
        self._client: Any = None
        self._initialize()

    def _initialize(self) -> None:
        """
        Configure the Gemini SDK and create the GenerativeModel client.

        Raises:
            AIAuthenticationError: If SDK configuration fails.
        """
        try:
            import google.generativeai as genai

            genai.configure(api_key=self._api_key)
            self._client = genai.GenerativeModel(self._model_name)
            self._genai = genai
            logger.info(
                "gemini_provider_initialized",
                extra={"model": self._model_name},
            )
        except ImportError as exc:
            raise AIProviderError(
                "google-generativeai package is not installed. "
                "Add it to requirements/base.txt."
            ) from exc
        except Exception as exc:
            raise AIAuthenticationError(
                f"Failed to initialize Gemini client: {exc}"
            ) from exc

    def validate_connection(self) -> bool:
        """
        Verify that the API key is valid by listing available models.

        Makes a lightweight ``list_models()`` call which requires valid
        credentials but does not consume inference quota.

        Returns:
            ``True`` if at least one model is returned.

        Raises:
            AIConnectionError: If the API is unreachable or credentials fail.
        """
        try:
            first_model = next(iter(self._genai.list_models()), None)
            is_valid: bool = first_model is not None
            logger.info(
                "gemini_connection_validated",
                extra={"model": self._model_name, "valid": is_valid},
            )
            return is_valid
        except Exception as exc:
            logger.error(
                "gemini_connection_validation_failed",
                extra={"model": self._model_name, "error": str(exc)},
            )
            raise AIConnectionError(
                f"Gemini API connection validation failed: {exc}"
            ) from exc

    def health_check(self) -> dict[str, Any]:
        """
        Return a health status dictionary for the Gemini provider.

        Calls ``validate_connection()`` and records the round-trip latency.
        Never raises — returns an ``"unhealthy"`` dict on failure so callers
        can include it in aggregate health responses without exception handling.

        Returns:
            Dict with keys: ``status``, ``provider``, ``model``, ``latency_ms``.
        """
        start: float = time.monotonic()
        try:
            self.validate_connection()
            latency_ms: float = (time.monotonic() - start) * 1000
            return {
                "status": "healthy",
                "provider": self.provider_name,
                "model": self._model_name,
                "latency_ms": round(latency_ms, 2),
            }
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning(
                "gemini_health_check_failed",
                extra={
                    "model": self._model_name,
                    "error": str(exc),
                    "latency_ms": round(latency_ms, 2),
                },
            )
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "model": self._model_name,
                "latency_ms": round(latency_ms, 2),
                "error": str(exc),
            }

    def complete(self, request: AIRequest) -> AIRawResponse:
        """
        Submit a prompt to Gemini and return the raw response.

        Not implemented in Phase 0. Will be fully implemented in Phase 4
        alongside the ContextBuilder, ResponseParser, budget enforcement,
        deduplication, and retry logic.

        Raises:
            NotImplementedError: Always, in Phase 0.
        """
        raise NotImplementedError(
            "GeminiProvider.complete() is not implemented in Phase 0. "
            "It will be implemented in Phase 4 alongside the ContextBuilder "
            "and ResponseParser. Set AI_PROVIDER=gemini and run Phase 4."
        )

    def close(self) -> None:
        """Release the Gemini client reference."""
        self._client = None
        logger.info(
            "gemini_provider_closed",
            extra={"model": self._model_name},
        )
