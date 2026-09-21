
import base64
from django.conf import settings
from django.db import models
from cryptography.fernet import Fernet

from core.models import BaseModel


def _get_fernet_key():
    """Derive a Fernet key from Django SECRET_KEY for credential encryption."""
    secret = settings.SECRET_KEY.encode()
    # Derive a 32-byte key using SHA-256 and take first 32 bytes
    import hashlib
    digest = hashlib.sha256(secret).digest()
    return Fernet(base64.urlsafe_b64encode(digest[:32]))


class ZerodhaCredentials(BaseModel):
    """
    Encrypted Zerodha API credentials stored in the database.
    Used as an alternative/or complement to .env environment variables.
    """
    account_id = models.CharField(
        max_length=100,
        help_text="User/account identifier for multi-tenancy",
        blank=True,
        null=True,
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
        help_text="Zerodha access token (short-lived, regenerated via login flow)",
    )
    request_token = models.CharField(
        max_length=500,
        help_text="Single-use Kite request token (out-of-band)",
        blank=True,
        null=True,
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
        max_length=50,
        default="ui",
        help_text="Source: ui|env|admin",
    )

    class Meta:
        verbose_name = "Zerodha Credentials"
        verbose_name_plural = "Zerodha Credentials"
        ordering = ["-is_active", "-created_at"]

    def __str__(self):
        return f"ZerodhaCredentials[{self.account_id or 'default'}]"

    def get_encrypted_api_key(self):
        """Return encrypted API key."""
        f = _get_fernet_key()
        return f.encrypt(self.api_key.encode()).decode()

    def set_encrypted_api_key(self, value):
        """Set encrypted API key."""
        f = _get_fernet_key()
        self.api_key = f.encrypt(value.encode()).decode()

    def get_encrypted_api_secret(self):
        """Return encrypted API secret."""
        f = _get_fernet_key()
        return f.encrypt(self.api_secret.encode()).decode()

    def set_encrypted_api_secret(self, value):
        """Set encrypted API secret."""
        f = _get_fernet_key()
        self.api_secret = f.encrypt(value.encode()).decode()

    def get_encrypted_access_token(self):
        """Return encrypted access token."""
        f = _get_fernet_key()
        return f.encrypt(self.access_token.encode()).decode()

    def set_encrypted_access_token(self, value):
        """Set encrypted access token."""
        f = _get_fernet_key()
        self.access_token = f.encrypt(value.encode()).decode()
