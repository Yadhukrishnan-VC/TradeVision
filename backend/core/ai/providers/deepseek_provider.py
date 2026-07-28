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
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, ClassVar

import httpx

from core.ai.base_provider import AIRawResponse, AIRequest, BaseAIProvider
from core.ai.exceptions import (
    AIAuthenticationError,
    AIConnectionError,
    AIProviderError,
    AIQuotaExceededError,
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

        Calls the DeepSeek chat completions API with retry logic for
        transient failures. Raises on authentication errors, quota
        exhaustion, and unrecoverable provider errors.

        Args:
            request: A fully populated ``AIRequest`` with a rendered prompt.

        Returns:
            ``AIRawResponse`` containing the raw LLM text and token metadata.

        Raises:
            AIAuthenticationError:   If the API key is rejected (401).
            AIRateLimitError:        If the provider rate limits the request (429).
            AIQuotaExceededError:    If provider quota is exhausted.
            AIConnectionError:       If the API is unreachable.
            AITimeoutError:          If the request times out.
            AIProviderError:         On any other provider-side error.
        """
        if self._client is None:
            raise AIProviderError("DeepSeek client is not initialised.")

        payload: dict[str, Any] = {
            "model": self._model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert trading and investment analyst. "
                               "Return your analysis as JSON following the specified schema.",
                },
                {"role": "user", "content": request.prompt},
            ],
            "max_tokens": request.max_tokens,
            "temperature": 0.1,
        }

        last_exception: Exception | None = None
        max_retries: int = 3
        for attempt in range(max_retries + 1):
            try:
                start: float = time.monotonic()
                response = self._client.post(
                    "/v1/chat/completions",
                    json=payload,
                )
                latency_ms: float = (time.monotonic() - start) * 1000

                if response.status_code == 200:
                    data: Any = response.json()
                    choices: list[Any] = data.get("choices", [])
                    if not choices:
                        raise AIProviderError(
                            "DeepSeek returned an empty choices list."
                        )
                    raw_text: str = choices[0].get("message", {}).get("content", "")
                    usage: Any = data.get("usage", {})
                    return AIRawResponse(
                        request_id=request.id,
                        provider=self.provider_name,
                        raw_text=raw_text,
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                        latency_ms=latency_ms,
                        estimated_cost_usd=Decimal(
                            str(data.get("estimated_cost", "0.000"))
                        ),
                        timestamp=datetime.now(timezone.utc),
                    )

                if response.status_code in (429, 503):
                    if attempt < max_retries:
                        wait: float = 2.0 * (2 ** attempt)
                        logger.warning(
                            "deepseek_rate_limited_retrying",
                            extra={
                                "attempt": attempt + 1,
                                "max_retries": max_retries,
                                "status_code": response.status_code,
                                "wait_seconds": wait,
                            },
                        )
                        time.sleep(wait)
                        continue
                    raise AIRateLimitError(
                        f"DeepSeek rate limited after {max_retries + 1} attempts. "
                        f"HTTP {response.status_code}: {response.text[:200]}"
                    )

                if response.status_code in (401, 403):
                    raise AIAuthenticationError(
                        "DeepSeek API rejected the API key. "
                        "Verify DEEPSEEK_API_KEY is correct and has not expired."
                    )

                if response.status_code == 402:
                    raise AIQuotaExceededError(
                        f"DeepSeek quota exhausted: {response.text[:200]}"
                    )

                raise AIProviderError(
                    f"DeepSeek API returned HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )

            except httpx.ConnectError as exc:
                last_exception = exc
                if attempt < max_retries:
                    wait = 2.0 * (2 ** attempt)
                    logger.warning(
                        "deepseek_connection_retrying",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "wait_seconds": wait,
                            "error": str(exc),
                        },
                    )
                    time.sleep(wait)
                    continue
                raise AIConnectionError(
                    f"DeepSeek API unreachable after {max_retries + 1} attempts: {exc}"
                ) from exc

            except httpx.TimeoutException as exc:
                last_exception = exc
                if attempt < max_retries:
                    wait = 2.0 * (2 ** attempt)
                    logger.warning(
                        "deepseek_timeout_retrying",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "wait_seconds": wait,
                            "error": str(exc),
                        },
                    )
                    time.sleep(wait)
                    continue
                raise AITimeoutError(
                    f"DeepSeek request timed out after {max_retries + 1} attempts: {exc}"
                ) from exc

            except (httpx.RequestError, httpx.HTTPError) as exc:
                last_exception = exc
                if attempt < max_retries:
                    wait = 2.0 * (2 ** attempt)
                    logger.warning(
                        "deepseek_request_retrying",
                        extra={
                            "attempt": attempt + 1,
                            "max_retries": max_retries,
                            "wait_seconds": wait,
                            "error": str(exc),
                        },
                    )
                    time.sleep(wait)
                    continue
                raise AIProviderError(
                    f"DeepSeek request failed after {max_retries + 1} attempts: {exc}"
                ) from exc

        raise AIProviderError(
            f"DeepSeek request failed after {max_retries + 1} attempts."
        )

    def close(self) -> None:
        """Release the ``httpx.Client``. Idempotent — safe to call multiple times."""
        if self._client is not None:
            self._client.close()
            self._client = None
            logger.info("deepseek_provider_closed")
