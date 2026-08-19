"""NEWS-FEED-1 — Celery tasks.

A single Beat-scheduled task polls the configured news provider for the
watchlist symbols every ``NEWS_POLL_INTERVAL_SECONDS`` (default 15 min). The
task:

- refuses to run when ingestion is disabled in settings,
- enforces the daily provider budget (budget-exhaustion is a logged skip),
- retries provider/rate-limit failures with exponential backoff (BaseTask,
  matching the recommendations/``AI_MAX_RETRIES`` pattern),
- never crashes the beat schedule — a failure at max retries is logged.

Re-runs are idempotent: dedup is enforced by the ``(source, url)`` unique
constraint in the repository.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from apps.news_feed.application.ingestion_service import get_ingestion_service
from apps.news_feed.domain.exceptions import NewsProviderError, NewsProviderRateLimited
from core.config import config
from core.tasks.base import BaseTask, INGESTION_MAX_RETRIES, INGESTION_RETRY_DELAY
from core.utils import generate_correlation_id

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    base=BaseTask,
    max_retries=INGESTION_MAX_RETRIES,
    default_retry_delay=INGESTION_RETRY_DELAY,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    acks_late=True,
    queue="maintenance",
    soft_time_limit=120,
    time_limit=180,
)
def ingest_news(self: Any) -> None:
    """Poll the news provider for the configured symbols and store headlines."""
    if not config.news_ingestion_enabled:
        logger.info("news_ingestion_disabled")
        return

    correlation_id = generate_correlation_id()
    service = get_ingestion_service()
    try:
        summary = service.run(correlation_id=correlation_id)
        logger.info(
            "news_ingestion_task_complete",
            extra={
                "fetched": summary["fetched"],
                "inserted": summary["inserted"],
                "skipped": summary["skipped"],
            },
        )
    except NewsProviderRateLimited as exc:
        logger.warning(
            "news_ingestion_task_rate_limited",
            extra={"error": str(exc), "attempt": self.request.retries},
        )
        raise self.retry(exc=exc)
    except NewsProviderError as exc:
        logger.exception(
            "news_ingestion_task_provider_failed",
            extra={"error": str(exc), "attempt": self.request.retries},
        )
        raise self.retry(exc=exc)
    except Exception as exc:  # never crash the beat schedule
        logger.exception(
            "news_ingestion_task_failed",
            extra={"error": str(exc)},
        )
