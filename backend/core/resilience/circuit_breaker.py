"""
TradeVision AI — Circuit breaker pattern.

Protects external service calls (market data APIs, news APIs, AI providers)
from cascading failures. State is stored in Redis so that all workers share
a single circuit state across the process boundary.

State machine::

    CLOSED ──[N failures]──▶ OPEN ──[TTL expires]──▶ HALF_OPEN
      ▲                                                    │
      └──────────[success in HALF_OPEN]───────────────────┘
                             │
                    [failure in HALF_OPEN]
                             │
                             ▼
                            OPEN (TTL reset)

Redis keys:
    circuit:{name}:open      — Exists with TTL when OPEN; expiry = HALF_OPEN
    circuit:{name}:failures  — Integer failure count; no TTL
"""

import logging
from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

import redis as redis_lib

from core.exceptions import CircuitBreakerOpenError
from core.metrics import CIRCUIT_BREAKER_STATE, CIRCUIT_BREAKER_TRIPS_TOTAL

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------


class CircuitState(str, Enum):
    """Possible states of a circuit breaker."""

    CLOSED = "closed"
    """Normal operation — calls pass through."""

    OPEN = "open"
    """Fault detected — calls are rejected immediately."""

    HALF_OPEN = "half_open"
    """Recovery probe — one call is allowed through."""


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class CircuitBreaker:
    """
    Redis-backed circuit breaker for external service calls.

    Args:
        name:              Unique identifier for this circuit (used as Redis key prefix).
        redis_client:      Injected Redis client. Never reads from Django settings
                           directly so the class is independently unit-testable.
        failure_threshold: Number of consecutive failures before opening the circuit.
        recovery_timeout:  Seconds the circuit stays OPEN before transitioning to HALF_OPEN.

    Example::

        breaker = CircuitBreaker("gemini-api", redis_client, failure_threshold=5)

        try:
            result = breaker.call(gemini_client.generate, prompt)
        except CircuitBreakerOpenError:
            return cached_response
    """

    def __init__(
        self,
        name: str,
        redis_client: redis_lib.Redis,  # type: ignore[type-arg]
        *,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
    ) -> None:
        """Initialise with injected Redis client and circuit configuration."""
        self._name = name
        self._redis = redis_client
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout

    # ------------------------------------------------------------------
    # Redis key helpers
    # ------------------------------------------------------------------

    @property
    def _open_key(self) -> str:
        return f"circuit:{self._name}:open"

    @property
    def _failures_key(self) -> str:
        return f"circuit:{self._name}:failures"

    # ------------------------------------------------------------------
    # State inspection
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """
        Return the current circuit state.

        Reads two Redis keys; the combination determines the state:
        - open key exists → OPEN
        - open key absent AND failures >= threshold → HALF_OPEN
        - open key absent AND failures < threshold → CLOSED
        """
        try:
            is_open = self._redis.exists(self._open_key)
            if is_open:
                return CircuitState.OPEN
            failures = int(self._redis.get(self._failures_key) or 0)
            if failures >= self._failure_threshold:
                return CircuitState.HALF_OPEN
            return CircuitState.CLOSED
        except redis_lib.RedisError:
            # If Redis is unavailable, fail open — allow the call through
            # rather than silently blocking all traffic.
            logger.warning(
                "circuit_breaker_redis_unavailable",
                extra={"breaker_name": self._name},
            )
            return CircuitState.CLOSED

    @property
    def failure_count(self) -> int:
        """Return the current failure count from Redis."""
        try:
            return int(self._redis.get(self._failures_key) or 0)
        except redis_lib.RedisError:
            return 0

    # ------------------------------------------------------------------
    # Call interception
    # ------------------------------------------------------------------

    def call(
        self,
        func: Callable[..., T],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute ``func`` through the circuit breaker.

        Raises:
            CircuitBreakerOpenError: If the circuit is OPEN.
            Exception:               Any exception raised by ``func`` is
                                     re-raised after recording the failure.

        Returns:
            The return value of ``func``.
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            logger.warning(
                "circuit_breaker_rejected",
                extra={"breaker_name": self._name, "state": current_state},
            )
            raise CircuitBreakerOpenError(self._name)

        try:
            result: T = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception:
            self._record_failure()
            raise

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _record_success(self) -> None:
        """Transition to CLOSED on success; reset all failure tracking."""
        try:
            pipe = self._redis.pipeline()
            pipe.delete(self._open_key)
            pipe.delete(self._failures_key)
            pipe.execute()
        except redis_lib.RedisError:
            logger.warning(
                "circuit_breaker_success_record_failed",
                extra={"breaker_name": self._name},
            )
        self._update_metric(CircuitState.CLOSED)

    def _record_failure(self) -> None:
        """Increment failure count; open the circuit when threshold is reached."""
        try:
            new_count = self._redis.incr(self._failures_key)
            if new_count >= self._failure_threshold:
                self._open_circuit()
        except redis_lib.RedisError:
            logger.warning(
                "circuit_breaker_failure_record_failed",
                extra={"breaker_name": self._name},
            )

    def _open_circuit(self) -> None:
        """Transition to OPEN and set the recovery TTL."""
        try:
            self._redis.set(self._open_key, "1", ex=self._recovery_timeout)
        except redis_lib.RedisError:
            return

        CIRCUIT_BREAKER_TRIPS_TOTAL.labels(service=self._name).inc()
        self._update_metric(CircuitState.OPEN)

        logger.error(
            "circuit_breaker_opened",
            extra={
                "breaker_name": self._name,
                "failure_threshold": self._failure_threshold,
                "recovery_timeout_seconds": self._recovery_timeout,
            },
        )

    def _update_metric(self, state: CircuitState) -> None:
        """Push circuit state to Prometheus (0=CLOSED, 1=OPEN, 2=HALF_OPEN)."""
        state_value = {"closed": 0, "open": 1, "half_open": 2}[state.value]
        CIRCUIT_BREAKER_STATE.labels(service=self._name).set(state_value)

    # ------------------------------------------------------------------
    # Manual controls (admin / testing)
    # ------------------------------------------------------------------

    def record_failure(self) -> None:
        """Public wrapper for recording a failure — exposed for admin and testing."""
        self._record_failure()

    def record_success(self) -> None:
        """Public wrapper for recording a success — exposed for admin and testing."""
        self._record_success()

    def reset(self) -> None:
        """
        Force the circuit to CLOSED state.

        Clears all Redis keys for this breaker. Use in tests or after
        a confirmed incident resolution.
        """
        try:
            pipe = self._redis.pipeline()
            pipe.delete(self._open_key)
            pipe.delete(self._failures_key)
            pipe.execute()
        except redis_lib.RedisError:
            pass
        self._update_metric(CircuitState.CLOSED)
        logger.info("circuit_breaker_reset", extra={"breaker_name": self._name})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class CircuitBreakerFactory:
    """
    Creates and caches named CircuitBreaker instances.

    Uses Django settings for default thresholds; individual breakers
    may override them at construction time.

    Args:
        redis_client: Shared Redis client injected at startup.
    """

    def __init__(self, redis_client: redis_lib.Redis) -> None:  # type: ignore[type-arg]
        """Initialise the factory with a shared Redis client."""
        self._redis = redis_client
        self._registry: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        *,
        failure_threshold: int | None = None,
        recovery_timeout: int | None = None,
    ) -> CircuitBreaker:
        """
        Return an existing CircuitBreaker by name or create a new one.

        Args:
            name:              Unique service identifier.
            failure_threshold: Override the default from Django settings.
            recovery_timeout:  Override the default from Django settings.
        """
        if name not in self._registry:
            from django.conf import settings

            self._registry[name] = CircuitBreaker(
                name=name,
                redis_client=self._redis,
                failure_threshold=failure_threshold
                or settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                recovery_timeout=recovery_timeout
                or settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
            )
        return self._registry[name]
