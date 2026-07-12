"""
TradeVision AI — Accounts application configuration.

Manages user identity, authentication, and role-based access control.
The custom ``User`` model defined here replaces Django's default user
via ``settings.AUTH_USER_MODEL = "accounts.User"``.
"""

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Configuration for the ``apps.accounts`` application."""

    name = "apps.accounts"
    verbose_name = "Accounts"
    default_auto_field = "django.db.models.BigAutoField"
