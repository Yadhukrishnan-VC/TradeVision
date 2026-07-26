"""
Tests for core.resilience.circuit_breaker — state transitions, fail-open,
and HALF_OPEN single-probe guarantee.
"""

import time
from unittest.mock import MagicMock, patch

import pytest
import redis as redis_lib

from core.resilience.circuit_breaker import CircuitBreaker, CircuitState
from core.exceptions import CircuitBreakerOpenError


def _mock_redis() -> MagicMock:
    """Create a mock Redis client that behaves like an in-memory store."""
    store: dict[str, str | int] = {}

    def _set(key, value, **kwargs):
        nx = kwargs.get("nx", False)
        if nx and key in store:
            return False
        store[key] = value
        return True

    def _delete(key):
        store.pop(key, None)
        return 1

    mock = MagicMock()
    mock.exists = MagicMock(side_effect=lambda k: k in store)
    mock.get = MagicMock(side_effect=lambda k: store.get(k))
    mock.incr = MagicMock(side_effect=lambda k: store.update({k: store.get(k, 0) + 1}) or store[k])
    mock.set = MagicMock(side_effect=_set)
    mock.delete = MagicMock(side_effect=_delete)

    pipe_mock = MagicMock()
    pipe_mock.set = MagicMock(side_effect=_set)
    pipe_mock.delete = MagicMock(side_effect=_delete)
    pipe_mock.execute = MagicMock(return_value=[True, 1])
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


class TestCircuitBreakerHalfOpenProbe:
    """HALF_OPEN state must allow exactly one concurrent probe call."""

    def test_probe_lock_acquired_in_half_open(self) -> None:
        """When in HALF_OPEN, the first caller must acquire the probe lock."""
        redis_client = _mock_redis()
        cb = CircuitBreaker(
            "probe-test", redis_client,
            failure_threshold=2, recovery_timeout=1, probe_lock_ttl=30,
        )
        # Force HALF_OPEN: reach threshold then let open key expire
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # Simulate open key expiry by deleting it
        cb._redis.delete(cb._open_key)
        assert cb.state == CircuitState.HALF_OPEN

        ok = cb._acquire_probe_lock()
        assert ok is True

    def test_second_caller_rejected_in_half_open(self) -> None:
        """When probe lock is held, a second caller must be rejected."""
        redis_client = _mock_redis()
        # Make set with nx=True return False when key exists
        store: dict[str, str | int] = {}

        def fake_set(key, value, **kwargs):
            nx = kwargs.get("nx", False)
            if nx and key in store:
                return False
            store[key] = value
            return True

        redis_client.set = MagicMock(side_effect=fake_set)
        redis_client.exists = MagicMock(side_effect=lambda k: k in store)
        redis_client.get = MagicMock(side_effect=lambda k: store.get(k))
        redis_client.incr = MagicMock(side_effect=lambda k: store.update({k: store.get(k, 0) + 1}) or store[k])
        redis_client.delete = MagicMock(side_effect=lambda k: store.pop(k, None))

        cb = CircuitBreaker(
            "probe-reject", redis_client,
            failure_threshold=2, recovery_timeout=1, probe_lock_ttl=30,
        )
        cb.record_failure()
        cb.record_failure()
        # Force HALF_OPEN
        cb._redis.delete(cb._open_key)
        assert cb.state == CircuitState.HALF_OPEN

        # Acquire lock
        assert cb._acquire_probe_lock() is True
        # Second attempt must fail
        assert cb._acquire_probe_lock() is False

    def test_half_open_call_proceeds_with_lock(self) -> None:
        """When in HALF_OPEN and probe lock is acquired, the call must proceed."""
        redis_client = _mock_redis()
        cb = CircuitBreaker(
            "probe-call", redis_client,
            failure_threshold=2, recovery_timeout=1, probe_lock_ttl=30,
        )
        cb.record_failure()
        cb.record_failure()
        cb._redis.delete(cb._open_key)

        result = cb.call(lambda: "success")
        assert result == "success"

    def test_half_open_rejects_when_probe_locked(self) -> None:
        """When in HALF_OPEN and probe lock is held, call() must raise."""
        redis_client = _mock_redis()
        cb = CircuitBreaker(
            "probe-reject-call", redis_client,
            failure_threshold=2, recovery_timeout=1, probe_lock_ttl=30,
        )
        cb.record_failure()
        cb.record_failure()
        cb._redis.delete(cb._open_key)

        # Acquire probe lock manually — simulate another caller
        cb._redis.set(cb._probe_key, "1", nx=True, ex=30)

        with pytest.raises(CircuitBreakerOpenError):
            cb.call(lambda: "should_not_run")

    def test_probe_success_closes_circuit(self) -> None:
        """A successful probe call must close the circuit (reset failures)."""
        redis_client = _mock_redis()
        cb = CircuitBreaker(
            "probe-close", redis_client,
            failure_threshold=2, recovery_timeout=60, probe_lock_ttl=30,
        )
        cb.record_failure()
        cb.record_failure()
        cb._redis.delete(cb._open_key)
        assert cb.state == CircuitState.HALF_OPEN

        cb.call(lambda: "ok")
        # After success, circuit should be CLOSED
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    def test_probe_failure_opens_circuit(self) -> None:
        """A failed probe call must reopen the circuit."""
        redis_client = _mock_redis()
        cb = CircuitBreaker(
            "probe-fail", redis_client,
            failure_threshold=2, recovery_timeout=60, probe_lock_ttl=30,
        )
        cb.record_failure()
        cb.record_failure()
        cb._redis.delete(cb._open_key)
        assert cb.state == CircuitState.HALF_OPEN

        class ProbeError(Exception):
            pass

        with pytest.raises(ProbeError):
            cb.call(lambda: (_ for _ in ()).throw(ProbeError("fail")))
        # After failure, circuit should be OPEN again
        assert cb.state == CircuitState.OPEN

    def test_probe_lock_ttl_expiry_allows_new_probe(self, clean_redis: redis_lib.Redis) -> None:
        """When probe lock TTL expires, a new caller must be able to acquire the probe."""
        cb = CircuitBreaker(
            "ttl-probe", clean_redis,
            failure_threshold=2, recovery_timeout=1, probe_lock_ttl=1,
        )
        cb.record_failure()
        cb.record_failure()
        clean_redis.delete(cb._open_key)
        assert cb.state == CircuitState.HALF_OPEN

        # Acquire probe lock (simulate first caller)
        acquired = cb._acquire_probe_lock()
        assert acquired is True

        # Second caller immediately cannot acquire
        assert cb._acquire_probe_lock() is False

        # Wait for TTL to expire
        time.sleep(1.1)

        # Now acquire should succeed again
        assert cb._acquire_probe_lock() is True
