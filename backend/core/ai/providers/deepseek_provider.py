"""
TradeVision AI — DeepSeek AI provider.

Phase 0 scope:
    ✓ SDK/client initialisation and authentication
    ✓ validate_connection() — verifies API key via GET /models
    ✓ health_check()        — returns latency and reachability
    ✓ close()               — releases httpx.Client
    ✗ complete()            — raises NotImplementedError (Phase 4)

Phase 4 will add:
    - complete() with full chat completion submission
    - Token counting and cost estimation
    - Retry logic with exponential backoff
    - Rate limit tracking via Redis
"""

import logging
import time
from typing import Any, ClassVar

import httpx

from core.ai.base_provider import AIRawResponse, AIRequest, BaseAIProvider
from core.ai.exceptions import (
    AIAuthenticationError,
    AIConnectionError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
)
from core.config import config

logger = logging.getLogger(__name__)


class DeepSeekProvider(BaseAIProvider):
    """
    DeepSeek AI provider — OpenAI-compatible chat completions API.

    Authenticates with the DeepSeek API using the provided API key and
    initialises an ``httpx.Client`` for the configured base URL.

    Args:
        api_key:    DeepSeek API key (from ``settings.DEEPSEEK_API_KEY``).
        base_url:   Base URL for the DeepSeek API.
        model_name: DeepSeek model identifier (e.g. ``"deepseek-chat"``).
    """

    provider_name: ClassVar[str] = "deepseek"

    def __init__(self, api_key: str, base_url: str, model_name: str) -> None:
        if not api_key:
            raise AIAuthenticationError(
                "DeepSeek API key must not be empty. "
                "Set DEEPSEEK_API_KEY in your environment configuration."
            )
        self._api_key: str = api_key
        self._base_url: str = base_url.rstrip("/")
        self._model_name: str = model_name
        self._client: httpx.Client | None = None
        self._initialize()

    def _initialize(self) -> None:
        """
        Create the ``httpx.Client`` with authentication headers.

        Raises:
            AIAuthenticationError: If client creation fails.
        """
        try:
            self._client = httpx.Client(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
            logger.info(
                "deepseek_provider_initialized",
                extra={"model": self._model_name, "base_url": self._base_url},
            )
        except Exception as exc:
            raise AIAuthenticationError(
                f"Failed to initialize DeepSeek client: {exc}"
            ) from exc

    def validate_connection(self) -> bool:
        """
        Verify that the API key is valid by listing available models.

        Makes a lightweight ``GET /v1/models`` call which requires valid
        credentials but does not consume inference quota.

        Returns:
            ``True`` if at least one model is returned.

        Raises:
            AIAuthenticationError: If credentials are rejected (401/403).
            AIConnectionError:     If the API is unreachable.
            AIRateLimitError:      If rate limited (429).
            AITimeoutError:        If the request times out.
        """
        if self._client is None:
            raise AIProviderError("DeepSeek client is not initialised.")

        try:
            response = self._client.get("/v1/models")
        except httpx.ConnectError as exc:
            raise AIConnectionError(
                f"DeepSeek API unreachable at {self._base_url}: {exc}"
            ) from exc
        except httpx.TimeoutException as exc:
            raise AITimeoutError(
                f"DeepSeek API request timed out: {exc}"
            ) from exc

        if response.status_code == 401 or response.status_code == 403:
            raise AIAuthenticationError(
                "DeepSeek API rejected the API key. "
                "Verify DEEPSEEK_API_KEY is correct and has not expired."
            )
        if response.status_code == 429:
            raise AIRateLimitError(
                "DeepSeek API rate limit exceeded during connection validation."
            )
        if response.status_code != 200:
            raise AIProviderError(
                f"DeepSeek API returned HTTP {response.status_code}: "
                f"{response.text[:200]}"
            )

        data: Any = response.json()
        models: list[Any] = data.get("data", [])
        is_valid: bool = len(models) > 0

        logger.info(
            "deepseek_connection_validated",
            extra={"model": self._model_name, "valid": is_valid},
        )
        return is_valid

    def health_check(self) -> dict[str, Any]:
        """
        Return a health status dictionary for the DeepSeek provider.

        Calls ``validate_connection()`` and records the round-trip latency.
        Returns ``"degraded"`` when the connection succeeds but latency
        exceeds ``config.ai_health_degraded_threshold_ms``.
        Never raises — returns an ``"unhealthy"`` dict on failure so callers
        can include it in aggregate health responses without exception handling.

        Returns:
            Dict with keys: ``status``, ``provider``, ``latency_ms``.
        """
        start: float = time.monotonic()
        try:
            self.validate_connection()
            latency_ms: float = (time.monotonic() - start) * 1000
            threshold: float = config.ai_health_degraded_threshold_ms
            status: str = "degraded" if latency_ms > threshold else "healthy"
            return {
                "status": status,
                "provider": self.provider_name,
                "latency_ms": round(latency_ms, 2),
            }
        except Exception as exc:
            latency_ms = (time.monotonic() - start) * 1000
            logger.warning(
                "deepseek_health_check_failed",
                extra={
                    "error": str(exc),
                    "latency_ms": round(latency_ms, 2),
                },
            )
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "latency_ms": round(latency_ms, 2),
                "error": str(exc),
            }

    def complete(self, request: AIRequest) -> AIRawResponse:
        """
        Submit a prompt to DeepSeek and return the raw response.

        Not implemented in Phase 0. Will be fully implemented in Phase 4
        alongside the ContextBuilder, ResponseParser, budget enforcement,
        deduplication, and retry logic.

        Raises:
            NotImplementedError: Always, in Phase 0.
        """
        raise NotImplementedError(
            "DeepSeekProvider.complete() is not implemented in Phase 0. "
            "It will be implemented in Phase 4 alongside the ContextBuilder "
            "and ResponseParser."
        )

    def close(self) -> None:
        """Release the ``httpx.Client``. Idempotent — safe to call multiple times."""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("deepseek_provider_closed")
