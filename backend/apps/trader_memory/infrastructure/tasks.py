from __future__ import annotations

import logging
from datetime import datetime

from celery import shared_task

from core.tasks.base import BaseTask, DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY

logger = logging.getLogger(__name__)


@shared_task(
    name="tradevision.trader_memory.record_memory_entry",
    queue="analytics",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def record_memory_entry(
    self,
    recommendation_id: str,
    event_type: str,
    payload: dict,
    occurred_at: str,
    correlation_id: str = "",
) -> dict:
    from apps.trader_memory.application.ledger_service import LedgerService

    try:
        occurred_dt = datetime.fromisoformat(occurred_at)
    except (ValueError, TypeError):
        from django.utils import timezone
        occurred_dt = timezone.now()

    service = LedgerService()
    entry = service.append_entry(
        recommendation_id=recommendation_id,
        event_type=event_type,
        payload=payload,
        occurred_at=occurred_dt,
    )

    return {
        "entry_id": str(entry.id),
        "recommendation_id": recommendation_id,
        "event_type": event_type,
    }


@shared_task(
    name="tradevision.trader_memory.rebuild_projection",
    queue="analytics",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def rebuild_projection(self, strategy_id: str) -> dict:
    from apps.trader_memory.application.memory_query_service import MemoryQueryService

    service = MemoryQueryService()
    projection = service.rebuild_projection(strategy_id)

    return {
        "strategy_id": strategy_id,
        "sample_size": projection.sample_size,
        "win_rate": str(projection.win_rate),
    }
