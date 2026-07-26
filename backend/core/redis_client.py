"""
TradeVision AI — Centralized Redis client factory.

Provides a single, connection-pooled ``redis.Redis`` client shared by every
Redis-backed subsystem (EventBus, CircuitBreaker, rate limiter, dedup window,
cost budget tracker).

Usage::

    from core.redis_client import get_redis_client

    client = get_redis_client()
    client.ping()

The underlying ``ConnectionPool`` is created lazily on the first call and
reused for the lifetime of the process. Every call to ``get_redis_client()``
returns a ``redis.Redis`` instance bound to that same pool.

Constructors of classes like ``EventBus`` and ``CircuitBreaker`` continue to
accept an injected ``redis_client`` parameter for testability — this module
is used only in the ``from_settings()`` / production construction path.
"""

from __future__ import annotations

import logging

import redis

logger = logging.getLogger(__name__)

_pool: redis.ConnectionPool | None = None


def get_redis_client() -> redis.Redis:
    """
    Return a ``redis.Redis`` client bound to a process-wide connection pool.

    The pool is created lazily on first access using ``settings.REDIS_URL``
    and ``settings.REDIS_MAX_CONNECTIONS``, then cached for subsequent calls.
    """
    global _pool

    if _pool is None:
        from django.conf import settings

        _pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
        )
        logger.info(
            "redis_pool_initialized",
            extra={
                "max_connections": settings.REDIS_MAX_CONNECTIONS,
                "url": settings.REDIS_URL,
            },
        )

    return redis.Redis(connection_pool=_pool)
