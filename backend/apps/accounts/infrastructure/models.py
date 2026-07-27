from __future__ import annotations

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.accounts.domain.value_objects import Role
from apps.common.infrastructure.model_mixins import TimestampedModel


class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, default="", blank=True)
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


class Account(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="accounts",
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "accounts_account"
        indexes = [
            models.Index(fields=["owner", "is_default"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({'default' if self.is_default else 'non-default'})"
