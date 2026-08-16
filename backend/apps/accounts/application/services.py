from __future__ import annotations

import hashlib
import secrets
import uuid
from typing import Any

from django.contrib.auth import authenticate
from django.db import transaction

from apps.accounts.domain.exceptions import (
    InvalidScopeError,
    InvalidTokenError,
    RevokedAPIKeyError,
)
from apps.common.domain.exceptions import NotFoundError, PermissionDeniedError
from apps.accounts.domain.value_objects import Role, Scope
from apps.accounts.infrastructure.models import APIKey, User
from apps.common.domain.exceptions import ValidationError


class JWTIssuerService:
    """Handles JWT token issuance and refresh.

    Wraps djangorestframework-simplejwt behind a stable interface
    so that no other module imports simplejwt directly.
    """

    def __init__(self) -> None:
        from rest_framework_simplejwt.tokens import RefreshToken

        self._token_class = RefreshToken

    def issue_tokens(self, user: User) -> dict[str, str]:
        """Issue an access + refresh token pair for the given user.

        Args:
            user: An authenticated Django User instance.

        Returns:
            A dict with ``access`` and ``refresh`` token strings.
        """
        refresh = self._token_class.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

    def refresh(self, refresh_token: str) -> dict[str, str]:
        """Refresh an access token using a valid refresh token.

        Args:
            refresh_token: The raw refresh token string.

        Returns:
            A dict with the new ``access`` token.

        Raises:
            InvalidTokenError: If the refresh token is invalid,
                expired, or has been blacklisted.
        """
        try:
            from rest_framework_simplejwt.tokens import RefreshToken as RefreshTokenClass
            token = RefreshTokenClass(refresh_token)
            return {
                "access": str(token.access_token),
                "refresh": str(token),
            }
        except Exception as exc:
            raise InvalidTokenError(
                message="Invalid or expired refresh token",
                code="invalid_refresh_token",
            ) from exc


class APIKeyService:
    """Manages API key lifecycle: creation, verification, and revocation."""

    def create_key(self, user: User, scopes: list[Scope]) -> tuple[APIKey, str]:
        """Create a new API key with the given scopes.

        Args:
            user: The user who will own the key.
            scopes: The list of scope strings to grant.

        Returns:
            A tuple of (APIKey instance, raw_key_string). The raw key
            is returned exactly once and is never persisted.

        Raises:
            InvalidScopeError: If any scope is not a valid Scope enum member.
        """
        self._validate_scopes(scopes)

        raw_key = secrets.token_urlsafe(32)
        key_hash = self._hash_key(raw_key)

        with transaction.atomic():
            api_key = APIKey.objects.create(
                user=user,
                key_hash=key_hash,
                scopes=[s.value for s in scopes],
            )

        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        import uuid as uuid_mod
        from apps.eventbus.domain.events import DomainEvent

        event = DomainEvent.create(
            event_type="accounts.PermissionChanged",
            payload={
                "user_id": str(user.id),
                "change_type": "api_key_created",
                "details": {"api_key_id": str(api_key.id), "scopes": [s.value for s in scopes]},
            },
            correlation_id=uuid_mod.uuid4(),
        )
        bus = get_event_bus()
        try:
            bus.publish(event)
        except Exception:
            pass

        return api_key, raw_key

    def verify_key(self, raw_key: str) -> APIKey:
        """Verify a raw API key and return the matching APIKey instance.

        Args:
            raw_key: The raw API key string to verify.

        Returns:
            The matching APIKey instance.

        Raises:
            NotFoundError: If no API key matches the given hash.
            RevokedAPIKeyError: If the key has been revoked.
        """
        key_hash = self._hash_key(raw_key)

        try:
            api_key = APIKey.objects.get(key_hash=key_hash)
        except APIKey.DoesNotExist:
            raise NotFoundError(
                message="API key not found",
                code="api_key_not_found",
            )

        if api_key.revoked_at is not None:
            raise RevokedAPIKeyError(
                message="API key has been revoked",
                code="api_key_revoked",
            )

        return api_key

    def revoke_key(self, api_key_id: uuid.UUID, actor: User) -> None:
        """Revoke an API key.

        Args:
            api_key_id: The UUID of the API key to revoke.
            actor: The user performing the revocation.

        Raises:
            NotFoundError: If the API key does not exist.
            PermissionDeniedError: If the actor is not the key owner
                and not an OWNER-role user.
        """
        try:
            api_key = APIKey.objects.get(id=api_key_id)
        except APIKey.DoesNotExist:
            raise NotFoundError(
                message="API key not found",
                code="api_key_not_found",
            )

        if api_key.user_id != actor.id and actor.role != Role.OWNER.value:
            raise PermissionDeniedError(
                message="You do not have permission to revoke this API key",
                code="cannot_revoke_key",
            )

        if api_key.revoked_at is not None:
            return

        with transaction.atomic():
            from django.utils import timezone
            api_key.revoked_at = timezone.now()
            api_key.save(update_fields=["revoked_at"])

        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        import uuid as uuid_mod
        from apps.eventbus.domain.events import DomainEvent

        event = DomainEvent.create(
            event_type="accounts.PermissionChanged",
            payload={
                "user_id": str(api_key.user_id),
                "change_type": "api_key_revoked",
                "details": {"api_key_id": str(api_key.id)},
            },
            correlation_id=uuid_mod.uuid4(),
        )
        bus = get_event_bus()
        try:
            bus.publish(event)
        except Exception:
            pass

    @staticmethod
    def _hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_scopes(scopes: list[Scope]) -> None:
        if not scopes:
            raise InvalidScopeError(
                message="At least one scope is required",
                code="invalid_scope",
                details={"invalid_scope": "empty list", "valid_scopes": sorted({s.value for s in Scope})},
            )
        valid_values = {s.value for s in Scope}
        for scope in scopes:
            if isinstance(scope, str):
                if scope not in valid_values:
                    raise InvalidScopeError(
                        message=f"Invalid scope: {scope}",
                        code="invalid_scope",
                        details={"invalid_scope": scope, "valid_scopes": sorted(valid_values)},
                    )
            elif isinstance(scope, Scope):
                pass
            else:
                raise InvalidScopeError(
                    message=f"Invalid scope type: {type(scope).__name__}",
                    code="invalid_scope_type",
                )
