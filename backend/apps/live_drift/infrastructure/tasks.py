"""Celery task for the live drift monitor (queue: ``monitoring``)."""

from __future__ import annotations

from typing import Any

from celery import shared_task
from django.conf import settings


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    queue="monitoring",
)
def evaluate_live_drift(self: Any) -> dict[str, Any]:
    """Rolling-window live-vs-backtest drift check for observed rules.

    No-op (logged, not an error) unless the broker adapter is paper — this
    monitor exists exclusively for the paper dress rehearsal and must never
    imply anything about live-capital behaviour.
    """
    broker_env = str(getattr(settings, "BROKER_ENVIRONMENT", "sandbox"))
    if broker_env == "live":
        from core.utils import get_now

        return {"skipped": True, "reason": "broker_environment=live", "at": get_now().isoformat()}

    from apps.live_drift.application.drift_monitor import evaluate_all_observations

    return evaluate_all_observations()
