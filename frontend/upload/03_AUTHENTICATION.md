# 03 — Authentication

## Critical Finding (VERIFIED) — Authentication Is Not Wired

`DEFAULT_AUTHENTICATION_CLASSES` is **empty** in the DRF settings, and NO view class registers a token/API-key authenticator except the login/refresh views which explicitly set `authentication_classes = []`.

```python
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_AUTHENTICATION_CLASSES": [],          # <-- empty
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    ...
}
```
SOURCE: `backend/config/settings/base.py:191`

Consequences:
- `IsAuthenticated` endpoints (the vast majority) currently return **403 Forbidden** for every request — there is no authenticator that can set `request.user`.
- `apps/common/infrastructure/authentication.py` defines `APIKeyAuthentication` (header `Authorization: Api-Key <raw_key>`) and `JWTAuthentication`, but they are **not registered** in settings or on views (only `login`/`refresh`/`webhooks` clear/relax auth).
- The login view itself works: it is `AllowAny` with no auth classes and issues JWTs.

## Login / Refresh Flow (VERIFIED)

- `POST /api/v1/auth/login/` (alias `POST /api/v1/auth/token/`):
  - Body: `{"username": "<str>", "password": "<str>"}`
  - Success (200): `{"access": "<jwt>", "refresh": "<jwt>", "user": {...}}`
  - Failures (401): `{"error": {"code": "invalid_credentials"|"account_disabled", "message": "..."}}`
  - SOURCE: `backend/apps/accounts/interfaces/api/views.py:27`
- `POST /api/v1/auth/refresh/` (alias `POST /api/v1/auth/token/refresh/`):
  - Body: `{"refresh": "<refresh_jwt>"}`
  - Success (200): `{"access": "<new>", "refresh": "<new>"}` (rotation on by default)
  - Failure (401): `{"error": {"code": "invalid_refresh_token", "message": "..."}}`
  - SOURCE: `backend/apps/accounts/interfaces/api/views.py:87`, `backend/config/settings/base.py:203` (ROTATE_REFRESH_TOKENS=True, BLACKLIST_AFTER_ROTATION=True)
- `GET /api/v1/auth/me/` — requires auth (`MeView`), returns `UserSerializer.data`. Currently unreachable (403) due to the auth gap. SOURCE: `backend/apps/accounts/interfaces/api/views.py:110`
- `GET/POST/DELETE /api/v1/auth/api-keys/` — APIKeyViewSet, `IsAuthenticated`; POST returns the raw key once. Currently unreachable (403). SOURCE: `backend/apps/accounts/interfaces/api/views.py:119`

## JWT Details (VERIFIED)

- `SIMPLE_JWT`: access lifetime 15 min default (`JWT_ACCESS_TOKEN_LIFETIME_MINUTES`), refresh 7 days, `AUTH_HEADER_TYPES: ("Bearer",)`, algorithm HS256, `USER_ID_FIELD: "id"`, claim `user_id`.
- SOURCE: `backend/config/settings/base.py:203`

## Legacy (Dead) Code — Do Not Use

`CustomTokenObtainPairView` / `CustomTokenObtainPairSerializer` exist in `backend/apps/accounts/views.py`, `serializers.py`, `urls.py` but are NOT wired into `config/urls.py`. Ignore them; use the `interfaces/api` endpoints above.
SOURCE: subagent audit (auth), `backend/config/urls.py` (no `accounts.urls` mount)

## API Keys (VERIFIED)

`APIKeyAuthentication` reads `Authorization: Api-Key <raw_key>`. `APIKeyService.create_key` returns `(api_key, raw_key)`; only the raw key is shown once at creation. Scopes are enum-based (`apps/accounts/domain/enums.py`).
SOURCE: `backend/apps/common/infrastructure/authentication.py`, `backend/apps/accounts/application/services.py`

## Frontend Implication

The frontend MUST still implement login + token refresh (the backend contract is real and used in tests), but it must treat every authenticated endpoint as **currently 403** until the backend wires an authenticator. This is a `BACKEND GAP` (see 12). Never invent a working token flow; document it as pending backend wiring.

## User Model (VERIFIED)

`AUTH_USER_MODEL = "accounts.User"` (`backend/config/settings/base.py:21`). `User(AbstractUser)`: UUID `id` pk, `username` unique default `""`, `role` field with choices `owner` / `staff` / `viewer` (default `viewer`). Owner/staff gate some endpoints (e.g. portfolio reconciliation).
SOURCE: `backend/apps/accounts/infrastructure/models.py`