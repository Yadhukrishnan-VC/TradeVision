"""
Tests for core.resilience.circuit_breaker — state transitions and fail-open.
"""

from unittest.mock import MagicMock, patch

from core.resilience.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:

    def test_initial_state_closed(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60)
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_reset_from_open(self) -> None:
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
