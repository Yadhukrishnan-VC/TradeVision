from __future__ import annotations

from django.urls import path

from apps.accounts.interfaces.api.views import APIKeyViewSet, LoginView, MeView, TokenRefreshView

urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("api-keys/", APIKeyViewSet.as_view(), name="auth-api-keys-list"),
    path("api-keys/<uuid:pk>/", APIKeyViewSet.as_view(), name="auth-api-keys-detail"),
]
