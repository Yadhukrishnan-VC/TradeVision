from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.domain.value_objects import Role
from apps.accounts.infrastructure.models import APIKey

pytestmark = pytest.mark.django_db

User = get_user_model()


class TestUserModel:
    def test_create_user_with_username(self) -> None:
        user = User.objects.create_user(username="testuser", password="testpass123")
        assert user.username == "testuser"
        assert user.check_password("testpass123")

    def test_default_role_is_viewer(self) -> None:
        user = User.objects.create_user(username="vieweruser", password="pass")
        assert user.role == Role.VIEWER.value

    def test_create_superuser(self) -> None:
        admin = User.objects.create_superuser(username="adminuser", password="adminpass")
        assert admin.is_superuser is True
        assert admin.is_staff is True

    def test_password_is_hashed(self) -> None:
        user = User.objects.create_user(username="hashuser", password="plaintext")
        assert user.password != "plaintext"
        assert user.check_password("plaintext") is True

    def test_str_representation(self) -> None:
        user = User.objects.create_user(username="struser", password="pass")
        assert str(user) == "struser (viewer)"


class TestAPIKeyModel:
    def test_create_api_key(self, user: object) -> None:
        api_key = APIKey.objects.create(
            user=user,  # type: ignore[arg-type]
            key_hash="abc123",
            scopes=["read:market_data"],
        )
        assert api_key.key_hash == "abc123"
        assert api_key.scopes == ["read:market_data"]
        assert api_key.revoked_at is None

    def test_revoked_key(self, user: object) -> None:
        from django.utils import timezone
        api_key = APIKey.objects.create(
            user=user,  # type: ignore[arg-type]
            key_hash="def456",
            scopes=["read:portfolio"],
            revoked_at=timezone.now(),
        )
        assert api_key.revoked_at is not None

    def test_api_key_str(self, user: object) -> None:
        api_key = APIKey.objects.create(
            user=user,  # type: ignore[arg-type]
            key_hash="ghi789",
            scopes=[],
        )
        assert str(api_key) == f"APIKey({api_key.id}) for {user.username}"
