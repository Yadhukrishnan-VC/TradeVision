"""
TradeVision AI — Accounts views.

Provides thin DRF views for authentication and user profile access.
Business logic (password reset, email verification, account deactivation)
belongs in a service layer that will be added in Phase 6.

Endpoints:
    POST /api/v1/auth/token/         Obtain JWT access + refresh tokens
    POST /api/v1/auth/token/refresh/ Exchange a refresh token for a new access token
    GET  /api/v1/auth/me/            Retrieve the authenticated user's profile
"""

import logging

from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import CustomTokenObtainPairSerializer, UserSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authentication views
# ---------------------------------------------------------------------------


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Obtain a JWT access + refresh token pair.

    Extends the standard simplejwt endpoint to embed ``role`` and ``email``
    in the token claims and include the serialised user profile in the
    response body.

    Request body::

        {
            "email": "trader@example.com",
            "password": "SecurePass123!"
        }

    Response body::

        {
            "access":  "<JWT access token>",
            "refresh": "<JWT refresh token>",
            "user": {
                "id": "<uuid>",
                "email": "trader@example.com",
                "role": "TRADER",
                ...
            }
        }
    """

    serializer_class = CustomTokenObtainPairSerializer
    throttle_scope = "auth"


# ---------------------------------------------------------------------------
# User profile view
# ---------------------------------------------------------------------------


class UserProfileView(generics.RetrieveAPIView):
    """
    Retrieve the authenticated user's profile.

    Returns the same ``UserSerializer`` payload embedded in the login
    response, useful for re-hydrating client-side state after a page reload.

    Authentication required: Bearer token in the ``Authorization`` header.

    GET /api/v1/auth/me/
    """

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self) -> object:
        """Return the currently authenticated user."""
        logger.debug(
            "user_profile_accessed",
            extra={"user_id": str(self.request.user.pk)},
        )
        return self.request.user
