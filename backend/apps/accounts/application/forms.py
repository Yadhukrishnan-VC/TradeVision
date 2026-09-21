"""
Django forms for Zerodha credential management.

Provides validation and cleaning for per-user Zerodha API credential input
via the web UI. Credentials are stored encrypted in the database via the
ZerodhaCredentials model.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from . import models as accounts_models


class ZerodhaCredentialsForm(forms.Form):
    """
    Form for users to input Zerodha API credentials via the UI.

    Fields correspond to the ZerodhaCredentials model. Input values are
    validated for format and then encrypted before storage.
    """

    api_key = forms.CharField(
        max_length=500,
        widget=forms.PasswordInput(attrs={"placeholder": "Zerodha API Key"}),
        label="API Key",
        help_text="Your Zerodha Kite Connect API key",
        strip=False,
    )

    api_secret = forms.CharField(
        max_length=500,
        widget=forms.PasswordInput(attrs={"placeholder": "Zerodha API Secret"}),
        label="API Secret",
        help_text="Your Zerodha API secret key",
        strip=False,
    )

    access_token = forms.CharField(
        max_length=1000,
        widget=forms.PasswordInput(attrs={"placeholder": "Zerodha Access Token"}),
        label="Access Token",
        help_text="Zerodha access token (short-lived, generated via login flow)",
        strip=False,
    )

    request_token = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Request Token (optional)"}),
        label="Request Token",
        help_text="Single-use Kite request token (obtained out-of-band via login flow)",
        strip=False,
        initial="",
    )

    product = forms.ChoiceField(
        choices=[
            ("MIS", "MIS - Intraday Square-off"),
            ("CNC", "CNC - Delivery"),
            ("NRML", "NRML - Normal"),
        ],
        initial="MIS",
        label="Product",
        help_text="Kite product code for order execution",
    )

    environment = forms.ChoiceField(
        choices=[
            ("sandbox", "Sandbox"),
            ("live", "Live"),
        ],
        initial="sandbox",
        label="Environment",
        help_text="Trading environment: sandbox or live",
    )

    class Meta:
        fields = [
            "api_key",
            "api_secret",
            "access_token",
            "request_token",
            "product",
            "environment",
        ]

    def clean(self):
        """Validate that required fields are present."""
        cleaned_data = super().clean()
        api_key = cleaned_data.get("api_key")
        api_secret = cleaned_data.get("api_secret")
        access_token = cleaned_data.get("access_token")

        if not api_key:
            raise ValidationError("API Key is required")
        if not api_secret:
            raise ValidationError("API Secret is required")
        if not access_token:
            raise ValidationError("Access Token is required")

        return cleaned_data

    def save(self, user=None, commit=True):
        """
        Save the form data to a ZerodhaCredentials instance.

        Credentials are encrypted at rest. If a user is provided, the
        credentials are associated with that user. Otherwise, global/system
        credentials are created (user=None).
        """
        from cryptography.fernet import Fernet
        import hashlib

        instance, created = accounts_models.ZerodhaCredentials.objects.get_or_create(
            user=user,
            defaults={},
        )

        if created:
            instance.created_via = self.cleaned_data.get("created_via", "ui")

        # Encrypt and store credentials
        secret = self._get_fernet_key()
        instance.set_encrypted_api_key(self.cleaned_data["api_key"])
        instance.set_encrypted_api_secret(self.cleaned_data["api_secret"])
        instance.set_encrypted_access_token(self.cleaned_data["access_token"])

        if self.cleaned_data.get("request_token"):
            f = self._get_fernet()
            instance.request_token = f.encrypt(
                self.cleaned_data["request_token"].encode()
            ).decode()

        instance.product = self.cleaned_data["product"]
        instance.environment = self.cleaned_data["environment"]
        instance.is_active = True

        if commit:
            instance.save()

        return instance

    def _get_fernet_key(self):
        """Derive a Fernet key from Django SECRET_KEY for credential encryption."""
        secret = self._get_secret_key()
        digest = hashlib.sha256(secret).digest()
        import base64
        return Fernet(base64.urlsafe_b64encode(digest[:32]))

    def _get_secret_key(self):
        """Get the Django SECRET_KEY."""
        from django.conf import settings
        return settings.SECRET_KEY.encode()


class ZerodhaCredentialsBulkImportForm(forms.Form):
    """
    Form for bulk import of Zerodha credentials (e.g., from .env migration).
    """

    credentials_json = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 10,
                "placeholder": 'JSON array of credential objects with keys: api_key, api_secret, access_token, environment, product',
            }
        ),
        label="Credentials JSON",
        help_text="JSON array of credential objects to import",
    )

    merge_mode = forms.ChoiceField(
        choices=[
            ("overwrite", "Overwrite existing credentials"),
            ("merge", "Merge with existing (keep active)"),
        ],
        initial="overwrite",
        label="Merge Mode",
        help_text="How to handle existing credentials",
    )

    def clean_credentials_json(self):
        """Validate and parse the JSON credentials data."""
        import json

        data = self.cleaned_data["credentials_json"]
        try:
            credentials = json.loads(data)
            if not isinstance(credentials, list):
                raise ValidationError("Credentials must be a JSON array")
            for i, cred in enumerate(credentials):
                if not isinstance(cred, dict):
                    raise ValidationError(
                        f"Credential item {i} must be an object"
                    )
                required = ["api_key", "api_secret", "access_token"]
                for field in required:
                    if field not in cred:
                        raise ValidationError(
                            f"Credential item {i} missing required field: {field}"
                        )
            return credentials
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e.message}")