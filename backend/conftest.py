"""
TradeVision AI — Project-wide pytest fixtures.

All fixtures in this module are available to every test in the project
without an explicit import. App-specific fixtures live in
apps/<app_name>/tests/conftest.py.

Fixture dependency tree:
    db (pytest-django built-in)
    └── user
    │   └── authenticated_client
    └── admin_user
        └── admin_client
"""

from __future__ import annotations

import uuid
from typing import Generator

import pytest
import redis as redis_lib
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


# ---------------------------------------------------------------------------
# HTTP client fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client() -> APIClient:
    """Unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def authenticated_client(api_client: APIClient, user: object) -> APIClient:
    """DRF test client pre-authenticated as a standard TRADER user."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client: APIClient, admin_user: object) -> APIClient:
    """DRF test client pre-authenticated as an ADMIN user."""
    api_client.force_authenticate(user=admin_user)
    return api_client


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user(db: object) -> object:
    """
    A standard TRADER user instance, persisted for the duration of the test.

    Uses ``db`` to ensure the database is available and the transaction is
    rolled back after the test completes.
    """
    User = get_user_model()
    return User.objects.create_user(
        email=f"trader-{uuid.uuid4().hex[:8]}@tradevision.test",
        password="SecurePass123!",
    )


@pytest.fixture
def admin_user(db: object) -> object:
    """
    A superuser / ADMIN user instance, persisted for the test transaction.
    """
    User = get_user_model()
    return User.objects.create_superuser(
        email=f"admin-{uuid.uuid4().hex[:8]}@tradevision.test",
        password="AdminPass123!",
    )


# ---------------------------------------------------------------------------
# Infrastructure fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def redis_client() -> Generator[redis_lib.Redis, None, None]:  # type: ignore[type-arg]
    """
    Session-scoped real Redis client.

    Marked ``scope="session"`` to avoid repeated connection overhead.
    Tests that write to Redis should use a unique key prefix to avoid
    cross-test pollution.
    """
    client: redis_lib.Redis = redis_lib.from_url(  # type: ignore[type-arg]
        settings.REDIS_URL,
        decode_responses=True,
    )
    yield client
    client.close()


@pytest.fixture
def clean_redis(redis_client: redis_lib.Redis) -> Generator[redis_lib.Redis, None, None]:  # type: ignore[type-arg]
    """
    Provide a Redis client and flush the test database after each test.

    Use this fixture only for tests that actually write to Redis, to
    avoid unnecessarily expensive FLUSHDB calls.
    """
    yield redis_client
    redis_client.flushdb()


@pytest.fixture
def correlation_id() -> str:
    """Return a fresh UUID4 string for use as a test correlation ID."""
    return str(uuid.uuid4())
