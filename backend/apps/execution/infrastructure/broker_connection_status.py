"""Broker connection-status publication for the dashboard summary.

The dashboard's ``broker_connection_status`` field is driven by
``broker.ConnectionStatusChanged`` events applied by the dashboard
portfolio-summary projector. This module is the producer: it publishes
immediately when a token is acquired / cleared, and provides a Celery Beat
task that re-publishes on any later transition (e.g. the access token
silently expiring at the next day's login-window reset).
"""
from __future__ import annotations

import logging
import uuid

from celery import shared_task

logger = logging.getLogger(__name__)

CONNECTED = "connected"
DEGRADED = "degraded"
DISCONNECTED = "disconnected"

_VERIFY_OK_KEY = "zerodha:shed:monitor:verified_ok"
_LAST_STATUS_KEY = "zerodha:shed:monitor:last_connection_status"
# After a successful live Kite profile check we treat the token as connected
# for this window, so the Beat task does not hammer /user/profile every tick.
_VERIFY_OK_TTL_SECONDS = 240
_MONITOR_INTERVAL_SECONDS = 60.0

_resolved_account_id: str | None = None


def resolve_default_account_id() -> str | None:
    """Return the account id that owns the broker session.

    Prefers ``settings.DEFAULT_ACCOUNT_ID`` (single-operator deployments) and
    otherwise falls back to the first active superuser. Resolved once per
    process.
    """
    global _resolved_account_id
    if _resolved_account_id is not None:
        return _resolved_account_id

    from django.conf import settings

    configured = getattr(settings, "DEFAULT_ACCOUNT_ID", "") or ""
    if configured:
        _resolved_account_id = str(configured)
        return _resolved_account_id

    from apps.accounts.infrastructure.models import User

    try:
        user = (
            User.objects.filter(is_superuser=True, is_active=True)
            .order_by("id")
            .first()
        )
    except Exception:  # noqa: BLE001 - never block trading config on resolution
        user = None
    if user is not None:
        _resolved_account_id = str(user.id)
        return _resolved_account_id

    logger.warning("broker_connection_status_no_account_resolved")
    return None


def publish_broker_connection_status(
    status: str,
    account_id: str | None = None,
) -> None:
    """Publish ``broker.ConnectionStatusChanged`` for the dashboard summary."""
    from apps.eventbus.domain.events import DomainEvent
    from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

    account_id = account_id or resolve_default_account_id()
    if not account_id:
        logger.warning("broker_connection_status_skipped_no_account")
        return

    event = DomainEvent.create(
        event_type="broker.ConnectionStatusChanged",
        payload={"account_id": str(account_id), "status": status},
        correlation_id=uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"broker.ConnectionStatusChanged:{status}",
        ),
        version=1,
    )
    try:
        get_event_bus().publish(event)
    except Exception:  # noqa: BLE001 - dashboard freshness never breaks broker
        logger.exception("broker_connection_status_publish_failed")
        return

    logger.info(
        "broker_connection_status_published",
        extra={"status": status, "account_id": str(account_id)},
    )


@shared_task(
    bind=True,
    max_retries=0,
    acks_late=True,
    queue="default",
)
def monitor_broker_connection(self) -> None:
    """Poll the configured Zerodha session and publish status transitions.

    Status derivation:
      * no access token configured -> ``disconnected``
      * token present and a Kite profile check succeeded within the last
        ``_VERIFY_OK_TTL_SECONDS`` -> ``connected`` (no live call needed)
      * otherwise -> live ``verify_access_token`` call; ``connected`` on
        success, ``disconnected`` on failure.

    Publishes only on an actual transition, tracked in Redis.
    """
    from apps.execution.application.zerodha_session_service import verify_access_token
    from core.config import config
    from core.redis_client import get_redis_client

    try:
        redis = get_redis_client()
        token = config.zerodha_access_token

        if not token:
            status = DISCONNECTED
            redis.delete(_VERIFY_OK_KEY)
        elif redis.get(_VERIFY_OK_KEY):
            status = CONNECTED
        elif verify_access_token(token):
            redis.set(_VERIFY_OK_KEY, "1", ex=_VERIFY_OK_TTL_SECONDS)
            status = CONNECTED
        else:
            redis.delete(_VERIFY_OK_KEY)
            status = DISCONNECTED

        last = redis.get(_LAST_STATUS_KEY)
        last_status = last.decode() if isinstance(last, bytes) else last
        if last_status == status:
            return

        redis.set(_LAST_STATUS_KEY, status)
        publish_broker_connection_status(status)
    except Exception:  # noqa: BLE001 - a flapping monitor must not crash beat
        logger.exception("broker_connection_monitor_failed")