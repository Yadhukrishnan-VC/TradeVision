"""
TradeVision AI — Accounts views.

Provides thin DRF views for authentication and user profile access.
Business logic (password reset, email verification, account deactivation)
belongs in a service layer that will be added in Phase 6.

Endpoints:
    POST /api/v1/auth/token/         Obtain JWT access + refresh tokens
    POST /api/v1/auth/token/refresh/ Exchange a refresh token for a new access token
    GET  /api/v1/auth/me/            Retrieve the authenticated user's profile
    POST /api/v1/zerodha/credentials/  Input/Update Zerodha API credentials via UI
"""

import logging

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import CustomTokenObtainPairSerializer, UserSerializer

from .forms import ZerodhaCredentialsForm, ZerodhaCredentialsBulkImportForm

from apps.accounts.infrastructure.models import ZerodhaCredentials as DBZerodhaCredentials

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


# ---------------------------------------------------------------------------
# Zerodha Credential management views
# ---------------------------------------------------------------------------


class ZerodhaCredentialsInputView(generics.CreateAPIView):
    """
    Accept Zerodha API credentials from the UI form.

    Accepts POST with api_key, api_secret, access_token, and optional
    request_token, product, and environment fields. Credentials are
    encrypted at rest and stored in the database, overriding any .env
    values for the duration of the session.

    Authentication not required (public endpoint for onboarding).
    On success, returns the stored credential summary and a success flag.

    Request body::

        {
            "api_key": "your_api_key",
            "api_secret": "your_api_secret",
            "access_token": "your_access_token",
            "request_token": "optional_request_token",
            "product": "MIS",
            "environment": "sandbox"
        }

    Response (201)::

        {
            "success": true,
            "source": "database|.env",
            "credentials": {
                "api_key": "*** masked ***",
                "environment": "sandbox",
                "product": "MIS"
            }
        }

    Response (400)::

        {
            "success": false,
            "errors": {
                "api_key": ["API Key is required"],
                ...
            }
        }
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = None

    def post(self, request, *args, **kwargs):
        form = ZerodhaCredentialsForm(data=request.data)

        if form.is_valid():
            instance = form.save(user=request.user if request.user.is_authenticated else None)

            # Return masked summary
            env = form.cleaned_data.get("environment", "sandbox")
            return Response(
                {
                    "success": True,
                    "source": "database" if instance.source == "database" else ".env",
                    "credentials": {
                        "api_key": "*** masked ***",
                        "environment": env,
                        "product": form.cleaned_data.get("product", "MIS"),
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {
                "success": False,
                "errors": form.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class ZerodhaCredentialsBulkImportView(generics.CreateAPIView):
    """
    Bulk import Zerodha credentials from JSON (e.g., migration from .env).

    Accepts POST with credentials_json (JSON array) and merge_mode.
    Each credential object must have: api_key, api_secret, access_token,
    and optionally environment, product.

    On success, returns the number of credentials imported/updated.
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = None

    def post(self, request, *args, **kwargs):
        form = ZerodhaCredentialsBulkImportForm(data=request.data)

        if form.is_valid():
            credentials_list = form.cleaned_data["credentials_json"]
            merge_mode = form.cleaned_data.get("merge_mode", "overwrite")

            imported = 0
            for cred_data in credentials_list:
                user = request.user if request.user.is_authenticated else None
                instance, created = DBZerodhaCredentials.objects.get_or_create(
                    user=user,
                    defaults={},
                )

                instance.set_encrypted_api_key(cred_data["api_key"])
                instance.set_encrypted_api_secret(cred_data["api_secret"])
                instance.set_encrypted_access_token(cred_data["access_token"])

                if "request_token" in cred_data and cred_data["request_token"]:
                    f = instance._get_fernet()
                    instance.request_token = f.encrypt(
                        cred_data["request_token"].encode()
                    ).decode()

                instance.product = cred_data.get("product", "MIS")
                instance.environment = cred_data.get("environment", "sandbox")
                instance.is_active = True
                instance.created_via = "env_import"
                instance.save()

                imported += 1

            return Response(
                {
                    "success": True,
                    "imported_count": imported,
                    "merge_mode": merge_mode,
                    "message": f"{imported} credential(s) imported successfully",
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {
                "success": False,
                "errors": form.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
