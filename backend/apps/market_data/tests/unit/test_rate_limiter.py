from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.market_data.infrastructure.rate_limiter import (
    CircuitAwareRateLimiter,
    TokenBucketRateLimiter,
)
from core.exceptions import CircuitBreakerOpenError
from core.resilience.circuit_breaker import CircuitBreakerFactory


class TestTokenBucketRateLimiter:
    @pytest.fixture
    def mock_redis(self) -> MagicMock:
        mock = MagicMock()
        mock.get.return_value = None
        return mock

    def test_initial_acquire_succeeds(self, mock_redis: MagicMock) -> None:
        limiter = TokenBucketRateLimiter(
            name="test",
            max_tokens=10,
            refill_rate=1.0,
            redis_client=mock_redis,
        )
        assert limiter.acquire() is True

    def test_exhausted_bucket_returns_false(self, mock_redis: MagicMock) -> None:
        mock_redis.get.return_value = 0.0
        limiter = TokenBucketRateLimiter(
            name="test",
            max_tokens=10,
            refill_rate=0.0,
            redis_client=mock_redis,
        )
        assert limiter.acquire() is False

    def test_reset(self, mock_redis: MagicMock) -> None:
        limiter = TokenBucketRateLimiter(
            name="test",
            max_tokens=10,
            refill_rate=1.0,
            redis_client=mock_redis,
        )
        limiter.reset()
        mock_redis.set.assert_called()


class TestCircuitAwareRateLimiter:
    @pytest.fixture
    def mock_breaker_factory(self) -> MagicMock:
        factory = MagicMock(spec=CircuitBreakerFactory)
        mock_breaker = MagicMock()
        mock_breaker.call.side_effect = lambda f, *a, **kw: f(*a, **kw)
        factory.get_or_create.return_value = mock_breaker
        return factory

    def test_successful_call(self, mock_breaker_factory: MagicMock) -> None:
        limiter = CircuitAwareRateLimiter(
            name="test",
            breaker_factory=mock_breaker_factory,
            max_tokens=10,
            refill_rate=10.0,
        )
        result = limiter.call(lambda: "success")
        assert result == "success"
