"""
Tests for the custom User model.

Covers:
- UUID primary key behaviour
- Email-only authentication (no username field)
- Role defaults and superuser role override
- Manager methods (create_user, create_superuser)
- Model property helpers (is_admin, is_trader)
- String representation
"""

import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import UserRole

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    """Unit tests for the custom User model and UserManager."""

    # ------------------------------------------------------------------
    # Primary key
    # ------------------------------------------------------------------

    def test_pk_is_uuid(self) -> None:
        """User primary key must be a UUID4 instance."""
        user = User.objects.create_user(
            email="pk-test@tradevision.test", password="pass"
        )
        assert isinstance(user.pk, uuid.UUID)
        assert user.pk.version == 4

    # ------------------------------------------------------------------
    # Email authentication
    # ------------------------------------------------------------------

    def test_username_field_is_email(self) -> None:
        """``USERNAME_FIELD`` must be ``email`` so simplejwt routes correctly."""
        assert User.USERNAME_FIELD == "email"

    def test_required_fields_is_empty(self) -> None:
        """No fields beyond email and password should be required."""
        assert User.REQUIRED_FIELDS == []

    def test_create_user_normalises_email(self) -> None:
        """Email domain part should be lowercased during normalisation."""
        user = User.objects.create_user(
            email="Test@TRADEVISION.TEST", password="pass"
        )
        assert user.email == "Test@tradevision.test"

    def test_create_user_requires_email(self) -> None:
        """Attempting to create a user with an empty email must raise ValueError."""
        with pytest.raises(ValueError, match="email"):
            User.objects.create_user(email="", password="pass")

    # ------------------------------------------------------------------
    # Role
    # ------------------------------------------------------------------

    def test_default_role_is_trader(self) -> None:
        """Newly created users must default to the TRADER role."""
        user = User.objects.create_user(
            email="trader-default@tradevision.test", password="pass"
        )
        assert user.role == UserRole.TRADER

    def test_superuser_role_is_admin(self) -> None:
        """Superusers must receive the ADMIN role automatically."""
        admin = User.objects.create_superuser(
            email="superuser@tradevision.test", password="adminpass"
        )
        assert admin.role == UserRole.ADMIN

    def test_superuser_has_staff_flag(self) -> None:
        """Superusers must have ``is_staff=True``."""
        admin = User.objects.create_superuser(
            email="staff@tradevision.test", password="adminpass"
        )
        assert admin.is_staff is True

    def test_superuser_has_superuser_flag(self) -> None:
        """Superusers must have ``is_superuser=True``."""
        admin = User.objects.create_superuser(
            email="super@tradevision.test", password="adminpass"
        )
        assert admin.is_superuser is True

    # ------------------------------------------------------------------
    # Property helpers
    # ------------------------------------------------------------------

    def test_is_admin_true_for_admin_role(self) -> None:
        """``is_admin`` must return True for ADMIN role users."""
        admin = User.objects.create_superuser(
            email="admin-prop@tradevision.test", password="pass"
        )
        assert admin.is_admin is True

    def test_is_admin_false_for_trader_role(self) -> None:
        """``is_admin`` must return False for TRADER role users."""
        trader = User.objects.create_user(
            email="trader-prop@tradevision.test", password="pass"
        )
        assert trader.is_admin is False

    def test_is_trader_true_for_trader_and_admin(self) -> None:
        """``is_trader`` must return True for both TRADER and ADMIN roles."""
        trader = User.objects.create_user(
            email="trader-check@tradevision.test", password="pass", role=UserRole.TRADER
        )
        admin = User.objects.create_superuser(
            email="admin-check@tradevision.test", password="pass"
        )
        assert trader.is_trader is True
        assert admin.is_trader is True

    def test_is_trader_false_for_read_only_role(self) -> None:
        """``is_trader`` must return False for READ_ONLY role users."""
        user = User.objects.create_user(
            email="readonly@tradevision.test", password="pass", role=UserRole.READ_ONLY
        )
        assert user.is_trader is False

    # ------------------------------------------------------------------
    # String representation
    # ------------------------------------------------------------------

    def test_str_returns_email(self) -> None:
        """``str(user)`` must return the user's email address."""
        user = User.objects.create_user(
            email="str-test@tradevision.test", password="pass"
        )
        assert str(user) == "str-test@tradevision.test"

    # ------------------------------------------------------------------
    # Password security
    # ------------------------------------------------------------------

    def test_password_is_hashed(self) -> None:
        """Passwords must never be stored in plain text."""
        user = User.objects.create_user(
            email="hash-test@tradevision.test", password="plaintext123"
        )
        assert user.password != "plaintext123"
        assert user.check_password("plaintext123") is True

    def test_check_wrong_password_returns_false(self) -> None:
        """``check_password`` must return False for an incorrect password."""
        user = User.objects.create_user(
            email="wrong-pw@tradevision.test", password="correct"
        )
        assert user.check_password("wrong") is False
