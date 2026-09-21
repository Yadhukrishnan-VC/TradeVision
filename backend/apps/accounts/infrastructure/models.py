from __future__ import annotations

import base64
import hashlib
import uuid

from cryptography.fernet import Fernet

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from core.models import BaseModel
from apps.accounts.domain.value_objects import Role
from apps.common.infrastructure.model_mixins import TimestampedModel


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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


class ZerodhaCredentials(BaseModel):
    """
    Encrypted Zerodha API credentials stored in the database per user.
    Serves as an alternative/complement to .env environment variables.
    Credentials are encrypted at rest using Fernet encryption derived from SECRET_KEY.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="zerodha_credentials",
        null=True,
        blank=True,
        help_text="User account these credentials belong to (null for global/system credentials)",
    )
    api_key = models.CharField(
        max_length=500,
        help_text="Zerodha Kite Connect API key",
    )
    api_secret = models.CharField(
        max_length=500,
        help_text="Zerodha API secret",
    )
    access_token = models.CharField(
        max_length=1000,
        help_text="Zerodha access token (short-lived; generated via Kite login flow)",
    )
    request_token = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Single-use Kite request token (out-of-band via login flow)",
    )
    product = models.CharField(
        max_length=20,
        default="MIS",
        help_text="Kite product code (MIS, CNC, etc.)",
    )
    environment = models.CharField(
        max_length=20,
        default="sandbox",
        help_text="Trading environment: sandbox | live",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether these credentials are currently active",
    )
    created_via = models.CharField(
        max_length=20,
        default="ui",
        help_text="Source of credentials: ui|env|admin",
    )

    class Meta:
        verbose_name = "Zerodha Credentials"
        verbose_name_plural = "Zerodha Credentials"
        ordering = ["-is_active", "-created_at"]

    def __str__(self) -> str:
        return f"ZerodhaCredentials[{self.user.username if self.user else 'system'}]"

    def _get_fernet(self):
        """Get Fernet instance for encrypting/decrypting credentials."""
        secret = settings.SECRET_KEY.encode()
        digest = hashlib.sha256(secret).digest()
        return Fernet(base64.urlsafe_b64encode(digest[:32]))

    def get_encrypted_api_key(self):
        """Return encrypted API key."""
        f = self._get_fernet()
        return f.encrypt(self.api_key.encode()).decode()

    def set_encrypted_api_key(self, value):
        """Set and encrypt API key."""
        f = self._get_fernet()
        self.api_key = f.encrypt(value.encode()).decode()

    def get_encrypted_api_secret(self):
        """Return encrypted API secret."""
        f = self._get_fernet()
        return f.encrypt(self.api_secret.encode()).decode()

    def set_encrypted_api_secret(self, value):
        """Set and encrypt API secret."""
        f = self._get_fernet()
        self.api_secret = f.encrypt(value.encode()).decode()

    def get_encrypted_access_token(self):
        """Return encrypted access token."""
        f = self._get_fernet()
        return f.encrypt(self.access_token.encode()).decode()

    def set_encrypted_access_token(self, value):
        """Set and encrypt access token."""
        f = self._get_fernet()
        self.access_token = f.encrypt(value.encode()).decode()

    @classmethod
    def get_active_credentials(cls, user=None):
        """Get active credentials, preferring DB over .env."""
        queryset = cls.objects.filter(is_active=True)
        if user:
            queryset = queryset.filter(user=user)
        # Try DB first, then fall back to .env
        try:
            credentials = queryset.latest("created_at")
            return {
                "api_key": credentials.api_key,
                "api_secret": credentials.api_secret,
                "access_token": credentials.access_token,
                "environment": credentials.environment,
                "source": "database",
            }
        except cls.DoesNotExist:
            from django.conf import settings
            return {
                "api_key": getattr(settings, "ZERODHA_API_KEY", ""),
                "api_secret": getattr(settings, "ZERODHA_API_SECRET", ""),
                "access_token": getattr(settings, "ZERODHA_ACCESS_TOKEN", ""),
                "environment": getattr(settings, "BROKER_ENVIRONMENT", "sandbox"),
                "source": ".env",
            }
