from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.domain.value_objects import Role
from apps.common.infrastructure.model_mixins import TimestampedModel


class User(AbstractUser):
    """Custom user model with role-based access control.

    Extends Django's AbstractUser with a role field for fine-grained
    authorization. The role determines which endpoints and operations
    the user may access.
    """

    role = models.CharField(
        max_length=16,
        choices=[(r.value, r.name) for r in Role],
        default=Role.VIEWER.value,
    )

    class Meta:
        db_table = "accounts_user"
        indexes = [
            models.Index(fields=["role"]),
        ]

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"


class APIKey(TimestampedModel):
    """Scoped API key for programmatic access.

    Only the SHA-256 hash of the key is persisted. The raw key is
    returned to the owner exactly once at creation time and cannot
    be retrieved afterwards.

    Revocation is one-directional: once ``revoked_at`` is set, the
    key cannot be un-revoked.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    key_hash = models.CharField(max_length=128, unique=True)
    scopes = models.JSONField(default=list)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "accounts_apikey"
        indexes = [
            models.Index(fields=["user", "revoked_at"]),
        ]

    def __str__(self) -> str:
        return f"APIKey({self.id}) for {self.user.username}"
