from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.accounts.application.services import JWTIssuerService
from apps.accounts.domain.exceptions import InvalidTokenError


class TestJWTIssuerService:
    @patch("rest_framework_simplejwt.tokens.RefreshToken")
    def test_issue_tokens_returns_access_and_refresh(
        self, mock_refresh_token_class: MagicMock
    ) -> None:
        mock_refresh = MagicMock()
        mock_refresh.access_token = MagicMock()
        mock_refresh.access_token.__str__.return_value = "access-token-123"
        mock_refresh.__str__.return_value = "refresh-token-456"
        mock_refresh_token_class.for_user.return_value = mock_refresh

        user = MagicMock()
        user.id = 1

        service = JWTIssuerService()
        result = service.issue_tokens(user)

        assert result["access"] == "access-token-123"
        assert result["refresh"] == "refresh-token-456"

    @patch("rest_framework_simplejwt.tokens.RefreshToken")
    def test_refresh_valid_token(self, mock_refresh_token_class: MagicMock) -> None:
        mock_token = MagicMock()
        mock_token.access_token = MagicMock()
        mock_token.access_token.__str__.return_value = "new-access-token"
        mock_token.__str__.return_value = "new-refresh-token"
        mock_refresh_token_class.return_value = mock_token

        service = JWTIssuerService()
        result = service.refresh("valid-refresh-token")

        assert result["access"] == "new-access-token"
        assert result["refresh"] == "new-refresh-token"

    @patch("rest_framework_simplejwt.tokens.RefreshToken")
    def test_refresh_invalid_token_raises_error(
        self, mock_refresh_token_class: MagicMock
    ) -> None:
        mock_refresh_token_class.side_effect = Exception("Token is invalid or expired")

        service = JWTIssuerService()
        with pytest.raises(InvalidTokenError):
            service.refresh("invalid-token")
