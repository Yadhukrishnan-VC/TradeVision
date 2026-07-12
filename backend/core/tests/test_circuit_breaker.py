"""
Tests for core.resilience.circuit_breaker — state transitions and fail-open.
"""

from unittest.mock import MagicMock, patch

import redis as redis_lib

from core.resilience.circuit_breaker import CircuitBreaker, CircuitState


def _mock_redis() -> MagicMock:
    """Create a mock Redis client that behaves like an in-memory store."""
    store: dict[str, str | int] = {}
    mock = MagicMock()
    mock.exists = MagicMock(side_effect=lambda k: k in store)
    mock.get = MagicMock(side_effect=lambda k: store.get(k))
    mock.incr = MagicMock(side_effect=lambda k: store.update({k: store.get(k, 0) + 1}) or store[k])
    mock.set = MagicMock(side_effect=lambda k, v, **kwargs: store.update({k: v}))
    mock.delete = MagicMock(side_effect=lambda k: store.pop(k, None))
    pipe_mock = MagicMock()
    pipe_mock.delete = MagicMock(side_effect=lambda k: store.pop(k, None))
    pipe_mock.execute = MagicMock(return_value=None)
    mock.pipeline = MagicMock(return_value=pipe_mock)
    return mock


class TestCircuitBreaker:

    def test_initial_state_closed(self) -> None:
        cb = CircuitBreaker("test", _mock_redis(), failure_threshold=3, recovery_timeout=60)
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker("test", _mock_redis(), failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_reset_from_open(self) -> None:
        cb = CircuitBreaker("test", _mock_redis(), failure_threshold=2, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
