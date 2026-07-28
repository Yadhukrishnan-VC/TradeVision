"""
TradeVision AI — Gemini AI provider.
"""

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, ClassVar

from core.ai.base_provider import AIRawResponse, AIRequest, BaseAIProvider
from core.ai.exceptions import (
    AIAuthenticationError,
    AIConnectionError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
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

        Calls the Gemini generate content API with retry logic for
        transient failures. Raises on authentication errors, quota
        exhaustion, and unrecoverable provider errors.

        Args:
            request: A fully populated ``AIRequest`` with a rendered prompt.

        Returns:
            ``AIRawResponse`` containing the raw LLM text and token metadata.

        Raises:
            AIAuthenticationError:   If the API key is rejected.
            AIRateLimitError:        If the provider rate limits the request.
            AIConnectionError:       If the API is unreachable.
            AITimeoutError:          If the request times out.
            AIProviderError:         On any other provider-side error.
        """
        if self._client is None:
            raise AIProviderError("Gemini client is not initialised.")

        max_retries: int = 3
        last_exception: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                start: float = time.monotonic()

                response = self._client.generate_content(
                    request.prompt,
                    generation_config=self._genai.types.GenerationConfig(
                        max_output_tokens=request.max_tokens,
                        temperature=0.1,
                    ),
                )

                latency_ms: float = (time.monotonic() - start) * 1000

                raw_text: str = response.text if response.text else ""

                try:
                    prompt_tokens: int = response.usage_metadata.prompt_token_count
                    completion_tokens: int = response.usage_metadata.candidates_token_count
                except (AttributeError, ValueError):
                    prompt_tokens = 0
                    completion_tokens = 0

                return AIRawResponse(
                    request_id=request.id,
                    provider=self.provider_name,
                    raw_text=raw_text,
                    input_tokens=prompt_tokens,
                    output_tokens=completion_tokens,
                    latency_ms=latency_ms,
                    estimated_cost_usd=Decimal("0.000"),
                    timestamp=datetime.now(timezone.utc),
                )

            except Exception as exc:
                exc_str: str = str(exc)

                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    if attempt < max_retries:
                        wait: float = 2.0 * (2 ** attempt)
                        logger.warning(
                            "gemini_rate_limited_retrying",
                            extra={
                                "attempt": attempt + 1,
                                "max_retries": max_retries,
                                "wait_seconds": wait,
                                "error": exc_str[:200],
                            },
                        )
                        time.sleep(wait)
                        continue
                    raise AIRateLimitError(
                        f"Gemini rate limited after {max_retries + 1} attempts: {exc_str[:200]}"
                    ) from exc

                if "API_KEY" in exc_str.upper() or "INVALID_ARGUMENT" in exc_str:
                    raise AIAuthenticationError(
                        f"Gemini API authentication failed: {exc_str[:200]}"
                    ) from exc

                if "timeout" in exc_str.lower() or "deadline" in exc_str.lower():
                    if attempt < max_retries:
                        wait = 2.0 * (2 ** attempt)
                        logger.warning(
                            "gemini_timeout_retrying",
                            extra={
                                "attempt": attempt + 1,
                                "max_retries": max_retries,
                                "wait_seconds": wait,
                                "error": exc_str[:200],
                            },
                        )
                        time.sleep(wait)
                        continue
                    raise AITimeoutError(
                        f"Gemini request timed out after {max_retries + 1} attempts: {exc_str[:200]}"
                    ) from exc

                if "unreachable" in exc_str.lower() or "connection" in exc_str.lower():
                    if attempt < max_retries:
                        wait = 2.0 * (2 ** attempt)
                        logger.warning(
                            "gemini_connection_retrying",
                            extra={
                                "attempt": attempt + 1,
                                "max_retries": max_retries,
                                "wait_seconds": wait,
                                "error": exc_str[:200],
                            },
                        )
                        time.sleep(wait)
                        continue
                    raise AIConnectionError(
                        f"Gemini API unreachable after {max_retries + 1} attempts: {exc_str[:200]}"
                    ) from exc

                if attempt < max_retries:
                    wait = 2.0 * (2 ** attempt)
                    logger.warning(
                        "gemini_retrying",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "wait_seconds": wait,
                            "error": exc_str[:200],
                        },
                    )
                    time.sleep(wait)
                    continue

                raise AIProviderError(
                    f"Gemini request failed after {max_retries + 1} attempts: {exc_str[:200]}"
                ) from exc

        raise AIProviderError(
            f"Gemini request failed after {max_retries + 1} attempts."
        )

    def close(self) -> None:
        """Release the Gemini client reference."""
        self._client = None
        logger.info(
            "gemini_provider_closed",
            extra={"model": self._model_name},
        )
