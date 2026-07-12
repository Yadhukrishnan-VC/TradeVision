"""
TradeVision AI — User model.

Replaces Django's default ``User`` with a custom model that:
- Uses email as the login identifier (no username field)
- Uses a UUID4 primary key for consistency with all domain models
- Carries a ``role`` field for coarse-grained RBAC
- Uses ``TextChoices`` for the role enum so Django admin and DRF
  serializers render human-readable labels automatically

This model must be referenced as ``settings.AUTH_USER_MODEL`` everywhere
(not imported directly) to prevent circular import issues.
"""

import logging
import uuid

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Role choices
# ---------------------------------------------------------------------------


class UserRole(models.TextChoices):
    """
    Coarse-grained role model for TradeVision AI users.

    Permissions are enforced at the DRF view layer via the permission
    classes in ``core.permissions``. This field is also embedded in
    JWT access tokens so the frontend can adapt its UI without an
    additional round-trip.
    """

    ADMIN = "ADMIN", "Administrator"
    """Full platform access including rule configuration and AI audit logs."""

    TRADER = "TRADER", "Trader"
    """Full read access plus personal write (watchlists, portfolio, alerts)."""

    READ_ONLY = "READ_ONLY", "Read Only"
    """Read-only access to market data and published recommendations."""


# ---------------------------------------------------------------------------
# User manager
# ---------------------------------------------------------------------------


class UserManager(BaseUserManager["User"]):
    """
    Custom manager for the ``User`` model.

    Uses email as the unique identifier instead of a username field.
    """

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: object,
    ) -> "User":
        """
        Create and persist a standard (non-super) user.

        Args:
            email:         The user's email address (case-normalised).
            password:      Plain-text password (hashed before storage).
            **extra_fields: Additional model fields (e.g. ``role``).

        Returns:
            The newly created ``User`` instance.

        Raises:
            ValueError: If ``email`` is empty.
        """
        if not email:
            raise ValueError("An email address is required to create a user.")

        email = self.normalize_email(email)
        user: User = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        logger.info("user_created", extra={"email": email})
        return user

    def create_superuser(
        self,
        email: str,
        password: str,
        **extra_fields: object,
    ) -> "User":
        """
        Create and persist a superuser with full admin privileges.

        Automatically sets ``is_staff``, ``is_superuser``, and
        ``role = ADMIN``. These values cannot be overridden via
        ``extra_fields`` to prevent accidental privilege escalation.

        Args:
            email:    The superuser's email address.
            password: Plain-text password (hashed before storage).

        Returns:
            The newly created superuser ``User`` instance.
        """
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        extra_fields["role"] = UserRole.ADMIN

        return self.create_user(email, password, **extra_fields)


# ---------------------------------------------------------------------------
# User model
# ---------------------------------------------------------------------------


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model for TradeVision AI.

    Key differences from Django's default ``User``:
    - **UUID primary key** — consistent with all other domain models
    - **Email-only authentication** — no ``username`` field
    - **Role field** — coarse RBAC via ``UserRole`` choices
    - **No ``first_name`` / ``last_name``** — not required for a trading platform

    Always reference this model as ``settings.AUTH_USER_MODEL`` or via
    ``django.contrib.auth.get_user_model()`` — never import it directly
    inside ``core/`` modules to avoid circular imports.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier (UUID4).",
    )
    email = models.EmailField(
        unique=True,
        db_index=True,
        help_text="Email address used for authentication.",
    )
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.TRADER,
        db_index=True,
        help_text="User role — determines permissions across the platform.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Designates whether this user account is active.",
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether this user can access the Django admin.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="UTC datetime when this account was created.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="UTC datetime when this account was last modified.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        """Return the user's email as the string representation."""
        return self.email

    def __repr__(self) -> str:
        """Return an unambiguous developer representation."""
        return f"<User pk={self.pk} email={self.email!r} role={self.role!r}>"

    @property
    def is_admin(self) -> bool:
        """Return True if this user has the ADMIN role."""
        return self.role == UserRole.ADMIN

    @property
    def is_trader(self) -> bool:
        """Return True if this user has the TRADER or ADMIN role."""
        return self.role in (UserRole.TRADER, UserRole.ADMIN)
