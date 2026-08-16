from __future__ import annotations

from typing import Any, Optional

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request

from apps.accounts.application.services import APIKeyService
from apps.accounts.domain.exceptions import RevokedAPIKeyError
from apps.common.domain.exceptions import NotFoundError


class APIKeyAuthentication(BaseAuthentication):
    """DRF authentication class that validates API keys.

    Expects the ``Authorization: Api-Key <raw_key>`` header format.
    On success, returns a ``(user, api_key)`` tuple for use by the
    rest of the request lifecycle.
    """

    def authenticate(self, request: Request) -> Optional[tuple[Any, Any]]:
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not auth_header.startswith("Api-Key "):
            return None

        raw_key = auth_header[len("Api-Key "):].strip()

        if not raw_key:
            return None

        service = APIKeyService()

        try:
            api_key = service.verify_key(raw_key)
        except RevokedAPIKeyError:
            raise AuthenticationFailed("API key has been revoked", code="api_key_revoked")
        except NotFoundError:
            raise AuthenticationFailed("Invalid API key.")
        except Exception as exc:
            raise AuthenticationFailed(str(exc))

        user = api_key.user

        if not user.is_active:
            raise AuthenticationFailed("User account is disabled.")

        return (user, api_key)
