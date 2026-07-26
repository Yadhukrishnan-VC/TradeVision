from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.accounts.domain.value_objects import Scope
from apps.accounts.infrastructure.models import APIKey, User


class LoginSerializer(serializers.Serializer):
    """Validates username and password for login."""

    username = serializers.CharField(required=True, write_only=True)
    password = serializers.CharField(required=True, write_only=True)


class TokenRefreshSerializer(serializers.Serializer):
    """Validates a refresh token."""

    refresh = serializers.CharField(required=True)


class APIKeyCreateSerializer(serializers.Serializer):
    """Validates API key creation requests."""

    scopes = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
    )

    def validate_scopes(self, value: list[str]) -> list[str]:
        valid_values = {s.value for s in Scope}
        invalid = [s for s in value if s not in valid_values]
        if invalid:
            raise serializers.ValidationError(
                f"Invalid scope(s): {', '.join(invalid)}. "
                f"Valid scopes: {', '.join(sorted(valid_values))}"
            )
        return value


class APIKeySerializer(serializers.ModelSerializer):
    """Read-only serializer for API keys that never exposes the key hash."""

    class Meta:
        model = APIKey
        fields = ["id", "scopes", "created_at", "updated_at", "revoked_at"]
        read_only_fields = ["id", "scopes", "created_at", "updated_at", "revoked_at"]


class UserSerializer(serializers.ModelSerializer):
    """Public user profile serializer."""

    class Meta:
        model = User
        fields = ["id", "username", "role", "date_joined"]
        read_only_fields = ["id", "username", "role", "date_joined"]


class APIKeyResponseSerializer(serializers.Serializer):
    """Response serializer for API key creation (includes the one-time raw key)."""

    id = serializers.UUIDField()
    raw_key = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
