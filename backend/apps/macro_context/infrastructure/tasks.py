"""MACRO-CONTEXT-1 — Celery tasks.

A single daily Beat-scheduled task ingests the point-in-time vintage history
of every supported series from FRED/ALFRED. Never retried: a missed run is
picked up by the next day's tick, and re-running is idempotent.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from apps.macro_context.application.macro_ingestion_service import (
    get_ingestion_service,
)
from core.config import config

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=0,
    acks_late=True,
    queue="maintenance",
    soft_time_limit=120,
)
def ingest_macro_series(self: Any) -> None:
    """Ingest the full macro vintage matrix from the configured provider.

    No-ops when macro ingestion is disabled in settings; a failure is
    logged (and isolated per series inside the service) without retrying.
    """
    if not config.macro_ingestion_enabled:
        logger.info("macro_ingestion_disabled")
        return
    try:
        summary = get_ingestion_service().run()
        logger.info(
            "macro_ingestion_task_complete",
            extra={
                "fetched": summary["fetched"],
                "inserted": summary["inserted"],
                "errors": len(summary["errors"]),
            },
        )
    except Exception as exc:
        logger.exception(
            "macro_ingestion_task_failed",
            extra={"error": str(exc)},
        )
