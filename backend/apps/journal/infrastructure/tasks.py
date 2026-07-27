from __future__ import annotations

import logging

from celery import shared_task

from apps.journal.infrastructure.repositories import JournalRepository

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    soft_time_limit=60,
    time_limit=90,
)
def finalize_stale_entries(self) -> int:
    repo = JournalRepository()
    stale_entries = repo.get_stale_entries()

    replayed_count = 0
    for entry in stale_entries:
        try:
            from apps.replay.application.replay_service import ReplayService
            ReplayService.replay(
                correlation_id=entry.correlation_id,
                target_consumer_group="journal",
            )
            replayed_count += 1
        except Exception:
            logger.exception(
                "Failed to replay events for stale journal entry",
                extra={"correlation_id": str(entry.correlation_id)},
            )

    return replayed_count
