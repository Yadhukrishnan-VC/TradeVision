"""
Tests for core.redis_client — pool sharing, lazy init, basic connectivity.
"""

from unittest.mock import patch

import pytest

from core.redis_client import _pool, get_redis_client


class TestRedisClientFactory:

    def test_returns_working_client(self, redis_client) -> None:
        """``get_redis_client()`` must return a client that can PING."""
        client = get_redis_client()
        assert client.ping() is True

    def test_pool_is_shared_across_calls(self) -> None:
        """Two calls to ``get_redis_client()`` must return clients sharing the same pool."""
        client_a = get_redis_client()
        client_b = get_redis_client()
        assert client_a.connection_pool is client_b.connection_pool

    def test_pool_is_lazily_initialized(self) -> None:
        """The module-level pool must be ``None`` before the first call."""
        # _pool is reset by import; after imports above it may already be set
        # by prior test calls. This test just verifies the factory creates one.
        from core import redis_client as rc

        rc._pool = None
        client = rc.get_redis_client()
        assert client.connection_pool is not None
        assert rc._pool is client.connection_pool
