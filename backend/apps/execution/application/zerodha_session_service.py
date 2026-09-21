"""Zerodha session helpers shared by the auth views and management command.

Handles building the environment-correct Kite login URL, exchanging a
single-use ``request_token`` for an ``access_token`` (persisting it both to
the active ``.env`` file and to the Redis hot override), and validating the
stored token against Kite.
"""
from __future__ import annotations

import logging
import os

from core.zerodha_runtime import clear_hot_access_token, set_hot_access_token

from apps.execution.infrastructure.brokers.zerodha_broker import (
    _SANDBOX_PASSTHROUGH_ROUTES,
    _SANDBOX_ROOT,
)
from core.config import config

logger = logging.getLogger(__name__)

PRODUCTION_ROOT = "https://api.kite.trade"
PRODUCTION_LOGIN_ROOT = "https://kite.trade"

_SANDBOX_API_KEY = "sandboxdemo"
_SANDBOX_API_SECRET = "sandboxdemo-secret"


# ---------------------------------------------------------------------------
# Login URL
# ---------------------------------------------------------------------------

def build_login_url() -> str:
    """Return the Kite login URL matching the current broker environment."""
    api_key = config.zerodha_api_key or _SANDBOX_API_KEY
    if config.broker_environment == "sandbox":
        root = _SANDBOX_ROOT
    else:
        root = PRODUCTION_LOGIN_ROOT
    return f"{root}/connect/login?api_key={api_key}&v=3"


# ---------------------------------------------------------------------------
# Client construction (sandbox-aware)
# ---------------------------------------------------------------------------

def _resolved_api_key() -> str:
    key = config.zerodha_api_key or ""
    if config.broker_environment == "sandbox" and not key:
        return _SANDBOX_API_KEY
    return key


def _resolved_api_secret() -> str:
    secret = config.zerodha_api_secret or ""
    if config.broker_environment == "sandbox" and not secret:
        return _SANDBOX_API_SECRET
    return secret


def build_kite_client():
    """Build a KiteConnect client with the correct root and sandbox routes."""
    from kiteconnect import KiteConnect

    api_key = _resolved_api_key()
    if config.broker_environment == "sandbox":
        client = KiteConnect(api_key=api_key, root=_SANDBOX_ROOT)
        routes = getattr(client, "_routes", {}) or {}
        client._routes = {
            key: value
            if key in _SANDBOX_PASSTHROUGH_ROUTES
            else "/oms" + value
            for key, value in routes.items()
        }
    else:
        client = KiteConnect(api_key=api_key)
    return client


# ---------------------------------------------------------------------------
# Access-token exchange
# ---------------------------------------------------------------------------

def exchange_request_token(request_token: str) -> str:
    """Exchange a single-use request token and persist the access token.

    Raises whatever Kite raises (SurfaceException with a readable message) so
    the caller can render the exact reason (invalid api_key, expired token,
    api_secret mismatch, ...).
    """
    client = build_kite_client()
    api_secret = _resolved_api_secret()
    api_key = _resolved_api_key()
    try:
        session = client.generate_session(request_token, api_secret=api_secret)
    except Exception as exc:
        logger.warning(
            "zerodha_access_token_exchange_failed",
            extra={
                "environment": config.broker_environment,
                "api_key": api_key,
                "reason": str(exc),
            },
        )
        raise
    access_token = session["access_token"]

    _persist_access_token(access_token)
    set_hot_access_token(access_token)

    logger.info(
        "zerodha_access_token_exchanged",
        extra={"environment": config.broker_environment},
    )
    return access_token


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

def verify_access_token(access_token: str) -> bool:
    """Return True when ``access_token`` authenticates against Kite.

    Uses ``/user/profile`` (a cheap read) and swallows transport/token errors
    into a boolean. ``None`` means "no token configured to test".
    """
    token = access_token or config.zerodha_access_token
    if not token:
        return False
    try:
        client = build_kite_client()
        client.set_access_token(token)
        data = client.profile()
        if isinstance(data, list):
            data = data[0] if data else {}
        return bool(data and (data.get("user_id") or data.get("user_name")))
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def active_env_path() -> str | None:
    """Path of the currently-active .env file writable from this process."""
    explicit = os.environ.get("ZERODHA_ENV_FILE", "")
    if explicit and os.path.exists(explicit):
        return explicit
    for candidate in ("/app/.env.active", "/app/.env"):
        if os.path.exists(candidate):
            return candidate
    return None


def _persist_access_token(access_token: str) -> str | None:
    env_path = active_env_path()
    if not env_path:
        logger.warning("zerodha_access_token_persist_skipped_no_env_file")
        return None

    env_lines = []
    env_updated = False
    with open(env_path, "r") as f:
        for line in f:
            stripped = line.strip()
            if stripped == "" or stripped.startswith("#"):
                env_lines.append(line)
                continue
            key, _, _ = stripped.partition("=")
            if key == "ZERODHA_ACCESS_TOKEN":
                env_lines.append(f"ZERODHA_ACCESS_TOKEN={access_token}")
                env_updated = True
            else:
                env_lines.append(line)

    if not env_updated:
        env_lines.append(f"ZERODHA_ACCESS_TOKEN={access_token}")

    with open(env_path, "w") as f:
        f.write("\n".join(env_lines))

    logger.info(
        "zerodha_access_token_persisted",
        extra={"env_path": env_path},
    )
    return env_path


def clear_persisted_access_token() -> None:
    clear_hot_access_token()
    env_path = active_env_path()
    if not env_path:
        return
    env_lines = []
    with open(env_path, "r") as f:
        for line in f:
            stripped = line.strip()
            key = stripped.partition("=")[0]
            if key == "ZERODHA_ACCESS_TOKEN":
                env_lines.append("ZERODHA_ACCESS_TOKEN=")
            else:
                env_lines.append(line)
    with open(env_path, "w") as f:
        f.write("\n".join(env_lines))