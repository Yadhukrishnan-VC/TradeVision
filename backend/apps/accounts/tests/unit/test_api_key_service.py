from __future__ import annotations

import uuid

import pytest

from apps.accounts.application.services import APIKeyService
from apps.accounts.domain.exceptions import InvalidScopeError, RevokedAPIKeyError
from apps.accounts.domain.value_objects import Role, Scope
from apps.accounts.infrastructure.models import APIKey
from apps.common.domain.exceptions import NotFoundError

pytestmark = pytest.mark.django_db


class TestAPIKeyService:
    def test_create_key_returns_key_and_raw_string(self, user: object) -> None:
        service = APIKeyService()
        api_key, raw_key = service.create_key(
            user=user,  # type: ignore[arg-type]
            scopes=[Scope.READ_MARKET_DATA],
        )
        assert api_key is not None
        assert raw_key is not None
        assert len(raw_key) > 0
        assert api_key.scopes == ["read:market_data"]

    def test_create_key_with_valid_scopes(self, user: object) -> None:
        service = APIKeyService()
        api_key, _ = service.create_key(
            user=user,  # type: ignore[arg-type]
            scopes=[Scope.READ_PORTFOLIO, Scope.READ_MARKET_DATA],
        )
        assert set(api_key.scopes) == {"read:portfolio", "read:market_data"}

    def test_create_key_with_invalid_scope_raises(self, user: object) -> None:
        service = APIKeyService()
        with pytest.raises(InvalidScopeError):
            service.create_key(
                user=user,  # type: ignore[arg-type]
                scopes=[Scope.READ_MARKET_DATA, "invalid:scope"],  # type: ignore[list-item]
            )

    def test_create_key_with_empty_scopes_raises(self, user: object) -> None:
        service = APIKeyService()
        with pytest.raises(InvalidScopeError):
            service.create_key(
                user=user,  # type: ignore[arg-type]
                scopes=[],
            )

    def test_verify_key_valid(self, user: object) -> None:
        service = APIKeyService()
        _, raw_key = service.create_key(
            user=user,  # type: ignore[arg-type]
            scopes=[Scope.READ_MARKET_DATA],
        )
        verified = service.verify_key(raw_key)
        assert verified.user == user

    def test_verify_key_not_found_raises(self, user: object) -> None:
        service = APIKeyService()
        with pytest.raises(NotFoundError):
            service.verify_key("nonexistent-key")

    def test_verify_revoked_key_raises(self, user: object) -> None:
        service = APIKeyService()
        api_key, raw_key = service.create_key(
            user=user,  # type: ignore[arg-type]
            scopes=[Scope.READ_MARKET_DATA],
        )
        service.revoke_key(api_key.id, actor=user)  # type: ignore[arg-type]

        with pytest.raises(RevokedAPIKeyError):
            service.verify_key(raw_key)

    def test_revoke_key_cannot_be_unrevoked(self, user: object) -> None:
        service = APIKeyService()
        api_key, _ = service.create_key(
            user=user,  # type: ignore[arg-type]
            scopes=[Scope.READ_MARKET_DATA],
        )
        service.revoke_key(api_key.id, actor=user)  # type: ignore[arg-type]

        api_key.refresh_from_db()
        assert api_key.revoked_at is not None

    def test_revoke_already_revoked_key_is_noop(self, user: object) -> None:
        service = APIKeyService()
        api_key, _ = service.create_key(
            user=user,  # type: ignore[arg-type]
            scopes=[Scope.READ_MARKET_DATA],
        )
        service.revoke_key(api_key.id, actor=user)  # type: ignore[arg-type]
        service.revoke_key(api_key.id, actor=user)  # type: ignore[arg-type]

    def test_non_owner_cannot_revoke_others_key(self, user: object) -> None:
        service = APIKeyService()
        api_key, _ = service.create_key(
            user=user,  # type: ignore[arg-type]
            scopes=[Scope.READ_MARKET_DATA],
        )

        other_user = type('obj', (object,), {
            'id': uuid.uuid4(),
            'role': Role.VIEWER.value,
        })

        from apps.common.domain.exceptions import PermissionDeniedError
        with pytest.raises(PermissionDeniedError):
            service.revoke_key(api_key.id, actor=other_user)  # type: ignore[arg-type]
