from __future__ import annotations

import logging
import time
from typing import Any

from core.redis_client import get_redis_client
from core.resilience.circuit_breaker import CircuitBreakerFactory, CircuitBreakerOpenError

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Redis-backed token bucket rate limiter for API calls.

    Uses the existing ``Redis`` client from ``core.redis_client`` and
    is designed to work alongside ``CircuitBreaker`` for comprehensive
    resilience.

    Args:
        name:            Unique identifier for this rate limiter.
        max_tokens:      Maximum number of tokens (burst capacity).
        refill_rate:     Tokens added per second.
        redis_client:    Redis client. Defaults to the shared process-wide client.
    """

    def __init__(
        self,
        name: str,
        max_tokens: int = 10,
        refill_rate: float = 1.0,
        redis_client: Any = None,
    ) -> None:
        self._name = name
        self._max_tokens = max_tokens
        self._refill_rate = refill_rate
        self._redis = redis_client or get_redis_client()

        self._tokens_key = f"ratelimit:{name}:tokens"
        self._ts_key = f"ratelimit:{name}:ts"

    def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire *tokens* from the bucket.

        Returns:
            ``True`` if the tokens were acquired (call allowed),
            ``False`` if the bucket is empty (call should be throttled).
        """
        now = time.time()
        current_tokens = self._get_tokens(now)

        if current_tokens >= tokens:
            remaining = current_tokens - tokens
            pipe = self._redis.pipeline()
            pipe.set(self._tokens_key, remaining)
            pipe.set(self._ts_key, now)
            pipe.execute()
            return True

        return False

    def _get_tokens(self, now: float) -> float:
        """Calculate the current number of tokens in the bucket.

        Applies the refill since the last update before returning.
        """
        current = float(self._redis.get(self._tokens_key) or self._max_tokens)
        last_ts = float(self._redis.get(self._ts_key) or now)

        elapsed = now - last_ts
        refill = elapsed * self._refill_rate
        return min(self._max_tokens, current + refill)

    def reset(self) -> None:
        """Reset the bucket to full capacity."""
        pipe = self._redis.pipeline()
        pipe.set(self._tokens_key, self._max_tokens)
        pipe.set(self._ts_key, time.time())
        pipe.execute()


class CircuitAwareRateLimiter:
    """Combines a circuit breaker with a rate limiter for HTTP fallback calls.

    This is a thin wrapper around the existing ``CircuitBreaker``
    mechanism. It reuses the breaker's failure-threshold behaviour as
    a rate-limiting signal: when the breaker is OPEN, calls are rejected
    regardless of the token bucket state.

    Args:
        name:            Unique name for the breaker+limiter pair.
        breaker_factory: A ``CircuitBreakerFactory`` instance from
                         ``core.resilience.circuit_breaker``.
        max_tokens:      Token bucket burst capacity.
        refill_rate:     Token bucket refill per second.
    """

    def __init__(
        self,
        name: str,
        breaker_factory: CircuitBreakerFactory,
        max_tokens: int = 10,
        refill_rate: float = 1.0,
    ) -> None:
        self._breaker = breaker_factory.get_or_create(name)
        self._limiter = TokenBucketRateLimiter(
            name=name,
            max_tokens=max_tokens,
            refill_rate=refill_rate,
        )
        self._name = name

    def call(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        """Execute *func* through the circuit breaker and rate limiter.

        Raises:
            CircuitBreakerOpenError: If the circuit is OPEN.
            Exception: Any exception from *func* is re-raised after
                recording the failure in the circuit breaker.
        """
        if not self._limiter.acquire():
            logger.warning(
                "rate_limiter_throttled",
                extra={"rate_limiter": self._name},
            )
            self._breaker.record_failure()
            raise CircuitBreakerOpenError(self._name)

        return self._breaker.call(func, *args, **kwargs)
