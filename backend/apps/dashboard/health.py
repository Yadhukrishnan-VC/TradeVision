from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.dashboard.infrastructure.common.event_log import EventLog

logger = logging.getLogger(__name__)


def check_trading_core_health() -> dict:
    """Health check for the trading core dashboard projection layer.

    Verifies that the latest EventLog entry for each projector is not
    older than 60 seconds (indicating stale projections).
    """
    result = {
        "status": "healthy",
        "latency_ms": None,
        "message": "",
        "detail": {},
    }

    projectors = [
        "position_projector",
        "order_projector",
        "trade_projector",
        "portfolio_summary_projector",
    ]

    cutoff = timezone.now() - timedelta(seconds=60)
    stale_found = False

    for projector in projectors:
        latest = EventLog.objects.filter(projector=projector).order_by("-applied_at").first()
        if latest is None:
            result["detail"][projector] = "no_events_processed"
            stale_found = True
        elif latest.applied_at < cutoff:
            result["detail"][projector] = f"stale_since={latest.applied_at.isoformat()}"
            stale_found = True
        else:
            result["detail"][projector] = "healthy"

    if stale_found:
        result["status"] = "degraded"
        result["message"] = "One or more projectors are stale"

    return result
