from __future__ import annotations

from django.urls import path

from apps.execution.interfaces.api.zerodha_auth_views import (
    ZerodhaAuthCallbackView,
    ZerodhaAuthStatusView,
    ZerodhaDisconnectView,
    ZerodhaLoginURLView,
)

urlpatterns = [
    path(
        "auth/login/",
        ZerodhaLoginURLView.as_view(),
        name="zerodha-auth-login",
    ),
    path(
        "auth/callback/",
        ZerodhaAuthCallbackView.as_view(),
        name="zerodha-auth-callback",
    ),
    path(
        "auth/status/",
        ZerodhaAuthStatusView.as_view(),
        name="zerodha-auth-status",
    ),
    path(
        "auth/disconnect/",
        ZerodhaDisconnectView.as_view(),
        name="zerodha-auth-disconnect",
    ),
]