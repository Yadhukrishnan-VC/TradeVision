from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from apps.accounts.infrastructure.models import User


class TokenPair:
    """Represents a JWT access and refresh token pair."""

    def __init__(self, access: str, refresh: str) -> None:
        self.access = access
        self.refresh = refresh


class TokenService(Protocol):
    """Abstract interface for JWT token operations.

    Concrete implementations wrap djangorestframework-simplejwt
    behind this interface so that no other part of the codebase
    imports simplejwt directly.
    """

    def issue_tokens(self, user: User) -> TokenPair:
        """Issue an access + refresh token pair for the given user."""
        ...

    def refresh(self, refresh_token: str) -> TokenPair:
        """Refresh an access token using a valid refresh token."""
        ...
