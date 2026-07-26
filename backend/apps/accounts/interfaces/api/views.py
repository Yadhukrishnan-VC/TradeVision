from __future__ import annotations

import uuid
from typing import Any

from django.contrib.auth import authenticate
from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.application.services import APIKeyService, JWTIssuerService
from apps.accounts.domain.value_objects import Role, Scope
from apps.accounts.infrastructure.models import APIKey, User
from apps.accounts.interfaces.api.serializers import (
    APIKeyCreateSerializer,
    APIKeyResponseSerializer,
    APIKeySerializer,
    LoginSerializer,
    TokenRefreshSerializer,
    UserSerializer,
)


class LoginView(APIView):
    """Authenticate with username/password and receive JWT tokens."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )

        if user is None:
            return Response(
                {"error": {"code": "invalid_credentials", "message": "Invalid username or password."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"error": {"code": "account_disabled", "message": "User account is disabled."}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        jwt_service = JWTIssuerService()
        tokens = jwt_service.issue_tokens(user)

        from apps.eventbus.domain.events import DomainEvent
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        event = DomainEvent.create(
            event_type="accounts.UserLoggedIn",
            payload={
                "user_id": str(user.id),
                "logged_in_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat(),
            },
            correlation_id=uuid.uuid4(),
        )

        try:
            bus = get_event_bus()
            bus.publish(event)
        except Exception:
            pass

        return Response(
            {
                "access": tokens["access"],
                "refresh": tokens["refresh"],
                "user": UserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class TokenRefreshView(APIView):
    """Refresh an expired access token using a valid refresh token."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        jwt_service = JWTIssuerService()

        try:
            tokens = jwt_service.refresh(serializer.validated_data["refresh"])
        except Exception as exc:
            return Response(
                {"error": {"code": "invalid_refresh_token", "message": str(exc)}},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(tokens, status=status.HTTP_200_OK)


class MeView(generics.RetrieveAPIView):
    """Return the current authenticated user's profile."""

    serializer_class = UserSerializer

    def get_object(self) -> User:
        return self.request.user  # type: ignore[return-value]


class APIKeyViewSet(generics.ListCreateAPIView, generics.DestroyAPIView):
    """Manage API keys for the authenticated user.

    GET  /api/v1/auth/api-keys/      — list own keys
    POST /api/v1/auth/api-keys/      — create a new key
    DELETE /api/v1/auth/api-keys/{id}/ — revoke a key
    """

    serializer_class = APIKeySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return APIKey.objects.filter(user=self.request.user)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = APIKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        scopes_data = serializer.validated_data["scopes"]
        scopes = [Scope(s) for s in scopes_data]

        service = APIKeyService()
        api_key, raw_key = service.create_key(user=request.user, scopes=scopes)

        response_serializer = APIKeyResponseSerializer(instance={
            "id": api_key.id,
            "raw_key": raw_key,
            "scopes": api_key.scopes,
        })
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        api_key_id = kwargs.get("pk")
        if not api_key_id:
            return Response(
                {"error": {"code": "missing_id", "message": "API key ID is required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = APIKeyService()

        try:
            service.revoke_key(api_key_id=uuid.UUID(str(api_key_id)), actor=request.user)
        except Exception as exc:
            return Response(
                {"error": {"code": "revocation_failed", "message": str(exc)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance: APIKey) -> None:
        pass
