from __future__ import annotations

import uuid
from typing import Generator

import pytest
import redis as redis_lib
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def authenticated_client(api_client: APIClient, user: object) -> APIClient:
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client: APIClient, admin_user: object) -> APIClient:
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def user(db: object) -> object:
    User = get_user_model()
    return User.objects.create_user(
        username=f"trader-{uuid.uuid4().hex[:8]}",
        password="SecurePass123!",
    )


@pytest.fixture
def admin_user(db: object) -> object:
    User = get_user_model()
    return User.objects.create_superuser(
        username=f"admin-{uuid.uuid4().hex[:8]}",
        password="AdminPass123!",
    )


@pytest.fixture(scope="session")
def redis_client() -> Generator[redis_lib.Redis, None, None]:
    client: redis_lib.Redis = redis_lib.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
    yield client
    client.close()


@pytest.fixture
def clean_redis(redis_client: redis_lib.Redis) -> Generator[redis_lib.Redis, None, None]:
    yield redis_client
    redis_client.flushdb()


@pytest.fixture
def correlation_id() -> str:
    return str(uuid.uuid4())
