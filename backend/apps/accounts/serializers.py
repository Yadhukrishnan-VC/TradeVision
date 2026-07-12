"""
TradeVision AI — Accounts serializers.

Provides:
- ``UserSerializer``              Read-only representation of a User
- ``CustomTokenObtainPairSerializer``  Extends JWT claims with role + email
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

logger = logging.getLogger(__name__)

User = get_user_model()


# ---------------------------------------------------------------------------
# User representation
# ---------------------------------------------------------------------------


class UserSerializer(serializers.ModelSerializer):
    """
    Read-only serialiser for the User model.

    Exposes only the fields safe for API consumers — deliberately excludes
    ``password``, ``groups``, ``user_permissions``, and internal flags.
    """

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "role",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields  # All fields are read-only on this serialiser


# ---------------------------------------------------------------------------
# JWT token serialiser
# ---------------------------------------------------------------------------


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends the standard JWT token pair serialiser to embed user context.

    Additional claims added to the access token payload:
    - ``role``  — the user's ``UserRole`` value (e.g. ``"TRADER"``)
    - ``email`` — the user's email address

    The ``validate()`` override also includes a ``user`` key in the
    response body so the client receives profile data without a second
    round-trip to ``/api/v1/auth/me/``.
    """

    @classmethod
    def get_token(cls, user: object) -> object:
        """
        Generate the JWT token and embed additional claims.

        Args:
            user: The authenticated ``User`` instance.

        Returns:
            A signed JWT token with ``role`` and ``email`` claims appended.
        """
        token = super().get_token(user)  # type: ignore[arg-type]
        # Embed user-specific claims to avoid extra API calls on the client
        token["role"] = user.role  # type: ignore[attr-defined]
        token["email"] = user.email  # type: ignore[attr-defined]
        return token

    def validate(self, attrs: dict) -> dict:
        """
        Validate credentials and return tokens plus serialised user data.

        The ``user`` key in the response allows the client to store
        profile information immediately after login without a follow-up
        call to ``/api/v1/auth/me/``.
        """
        data: dict = super().validate(attrs)
        # Attach the serialised user profile alongside the token pair
        data["user"] = UserSerializer(self.user).data  # type: ignore[attr-defined]
        logger.info(
            "user_logged_in",
            extra={"email": self.user.email, "role": self.user.role},  # type: ignore[attr-defined]
        )
        return data
