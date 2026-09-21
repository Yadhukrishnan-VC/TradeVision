"""
TradeVision AI — Accounts URL configuration.

Included under ``/api/v1/auth/`` in ``config/urls.py``.

Routes:
    POST /api/v1/auth/token/          Obtain access + refresh token pair
    POST /api/v1/auth/token/refresh/  Refresh an expired access token
    GET  /api/v1/auth/me/             Retrieve the authenticated user's profile
    POST /api/v1/zerodha/credentials/  Input/Update Zerodha API credentials via UI

Token blacklisting on logout will be added in Phase 6 (User & Portfolio).
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import CustomTokenObtainPairView, UserProfileView, ZerodhaCredentialsInputView, ZerodhaCredentialsBulkImportView

app_name = "accounts"

urlpatterns = [
    path(
        "token/",
        CustomTokenObtainPairView.as_view(),
        name="token-obtain",
    ),
    path(
        "token/refresh/",
        TokenRefreshView.as_view(),
        name="token-refresh",
    ),
    path(
        "me/",
        UserProfileView.as_view(),
        name="profile",
    ),
    path(
        "zerodha/credentials/",
        ZerodhaCredentialsInputView.as_view(),
        name="zerodha-credentials-input",
    ),
    path(
        "zerodha/credentials/bulk-import/",
        ZerodhaCredentialsBulkImportView.as_view(),
        name="zerodha-credentials-bulk-import",
    ),
]