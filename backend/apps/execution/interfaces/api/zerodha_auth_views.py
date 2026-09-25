"""Zerodha Kite Connect auth helper endpoints.

- ``GET /api/v1/zerodha/auth/login/``    — returns the environment-correct
  Kite login URL (browser opens it; Kite redirects back to the callback).
- ``GET /api/v1/zerodha/auth/callback/`` — auto-exchanges the single-use
  ``request_token`` Kite sends back, persists the access token (env file +
  Redis hot override) and shows a success/error page.
- ``GET /api/v1/zerodha/auth/status/``   — reports whether a token exists and
  (optionally) whether it still authenticates against Kite.

These endpoints are deliberately unauthenticated: they are the OAuth-style
redirect target the browser hits after the Kite login. They expose no secrets
and only ever process single-use tokens the caller must obtain from Kite.
"""
from __future__ import annotations

import logging

from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.execution.application.zerodha_session_service import (
    active_env_path,
    build_kite_client,
    build_login_url,
    exchange_request_token,
    verify_access_token,
)
from core.config import config
from core.zerodha_runtime import get_hot_access_token, hot_token_ttl

logger = logging.getLogger(__name__)

_HTML_CSS = """
body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;
display:flex;min-height:90vh;align-items:center;justify-content:center;
background:#0f172a;color:#e2e8f0;margin:0}
.card{background:#1e293b;border:1px solid #334155;border-radius:12px;
padding:2rem 2.5rem;max-width:560px;width:92%;box-shadow:0 10px 40px rgba(0,0,0,.4)}
h1{font-size:1.25rem;margin:0 0 .5rem}
code{background:#0f172a;padding:.15rem .4rem;border-radius:6px;font-size:.85rem;color:#7dd3fc}
.ok{color:#4ade80}.err{color:#f87171}.muted{color:#94a3b8;font-size:.85rem}
ol{margin:.5rem 0 1rem;padding-left:1.25rem}li{margin:.25rem 0}
a.btn{display:inline-block;margin-top:1rem;padding:.5rem 1rem;border-radius:8px;
background:#6366f1;color:#fff;text-decoration:none}
"""


def _html_page(title: str, body: str, kind: str = "ok") -> HttpResponse:
    return HttpResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{title}</title><style>{_HTML_CSS}</style></head>
<body><div class="card"><h1 class="{kind}">{title}</h1>{body}</div></body></html>""",
        content_type="text/html; charset=utf-8",
    )


class ZerodhaLoginURLView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        login_url = build_login_url()
        callback_url = request.build_absolute_uri("/api/v1/zerodha/auth/callback/")
        return Response(
            {
                "login_url": login_url,
                "environment": config.broker_environment,
                "callback_url": callback_url,
            }
        )


class ZerodhaAuthCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        request_token = (request.GET.get("request_token") or "").strip()
        status = (request.GET.get("status") or "").strip().lower()
        wants_json = request.GET.get("format", "").lower() == "json" or (
            request.GET.get("_format", "").lower() == "json"
        )

        if status and status != "success":
            message = f"Kite reported the login as {status!r}."
            return self._render(request_token, None, message, wants_json)

        if not request_token:
            return self._render(None, None, "No request_token was provided.", wants_json)

        try:
            access_token = exchange_request_token(request_token)
        except Exception as exc:  # noqa: BLE001
            reason = str(exc) or type(exc).__name__
            return self._render(request_token, reason, None, wants_json)

        return self._render(request_token, None, None, wants_json, success_token=access_token)

    def _render(self, request_token, error_reason, status_message, wants_json, success_token=None):
        if wants_json:
            if success_token:
                return Response({"success": True, "access_token_set": True, "message": "Connected."})
            return Response(
                {
                    "success": False,
                    "error": error_reason or status_message or "Missing request_token",
                    "error_type": "ZerodhaAuthError",
                },
                status=400,
            )

        if success_token:
            env_path = active_env_path()
            return _html_page(
                "Zerodha connected",
                f"<p class=\"ok\">Access token received and persisted.</p>"
                f"<p class=\"muted\">Environment: <code>{config.broker_environment}</code></p>"
                f"<p class=\"muted\">Persisted to: <code>{env_path or 'redis-hot'}</code></p>"
                f"<p class=\"muted\">The running stack picked up the token immediately "
                f"via the Redis hot override. A subsequent container recreate "
                f"(<code>make up</code>) reads it from the env file.</p>"
                f"<p class=\"muted\">Token expires at the next day's login-window reset — "
                f"repeat this login each trading day.</p>"
                f"<p><a class=\"btn\" href=\"/\">Back to dashboard</a></p>",
            )

        hint = _hint_for(reason=error_reason, has_request_token=bool(request_token))
        return _html_page(
            "Zerodha login failed",
            f"<p class=\"err\">{_escape_html(error_reason or status_message or 'Unknown error')}</p>"
            f"<p class=\"muted\">{_escape_html(hint)}</p>",
            kind="err",
        )


class ZerodhaAuthStatusView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        from django.conf import settings

        hot_token = get_hot_access_token() or ""
        api_key_present = bool(config.zerodha_api_key)
        env_token_present = bool(getattr(settings, "ZERODHA_ACCESS_TOKEN", ""))

        status = {
            "environment": config.broker_environment,
            "api_key_present": api_key_present,
            "access_token_env": env_token_present,
            "access_token_hot": bool(hot_token),
            "hot_token_ttl_seconds": hot_token_ttl(),
            "login_url": build_login_url(),
            "callback_url": "/api/v1/zerodha/auth/callback/",
            "connected": False,
            "checked_at": None,
        }

        if request.GET.get("verify") == "1":
            status["connected"] = verify_access_token(hot_token or config.zerodha_access_token)
            from datetime import datetime, timezone

            status["checked_at"] = datetime.now(timezone.utc).isoformat()

        return Response(status)


class ZerodhaDisconnectView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def delete(self, request):
        from apps.execution.application.zerodha_session_service import (
            clear_persisted_access_token,
        )

        clear_persisted_access_token()
        return Response({"success": True, "message": "Access token cleared."})


def _escape_html(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _hint_for(reason: str | None, has_request_token: bool) -> str:
    reason = reason or ""
    if "api_key" in reason.lower():
        return (
            "Kite rejected the API key. Confirm the ZERODHA_API_KEY in infra/.env "
            "matches the app in the Kite developer console, and that you logged in "
            "with that exact key. Production keys fail on sandbox and vice-versa."
        )
    if "expired" in reason.lower() or "invalid" in reason.lower():
        return (
            "The request_token is single-use and valid for roughly a minute. If you "
            "copied it earlier, log in again and let this page handle it automatically. "
            "A persistent error also indicates the ZERODHA_API_SECRET does not match "
            "the API key — verify the pair in infra/.env."
        )
    return "See the message above; the most common cause is a key/secret mismatch in infra/.env."