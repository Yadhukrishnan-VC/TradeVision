"""PIPELINE-HEALTH-1 — Celery tasks.

A single Beat-scheduled task runs the health evaluation. The evaluation
itself is a no-op outside market hours (see ``HealthEvaluationService``).
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=0,
    acks_late=True,
    queue="maintenance",
    soft_time_limit=25,
)
def evaluate_pipeline_health(self: Any) -> None:
    """Evaluate and persist a pipeline health snapshot (Beat, every 30s).

    No-ops outside market hours; never retried (a missed evaluation is
    picked up by the next Beat tick 30s later).
    """
    from apps.pipeline_health.application.health_evaluation_service import (
        get_health_evaluation_service,
    )

    try:
        status = get_health_evaluation_service().evaluate()
        logger.info(
            "pipeline_health_evaluation_complete",
            extra={"overall_status": status.value},
        )
    except Exception as exc:
        logger.exception(
            "pipeline_health_evaluation_failed",
            extra={"error": str(exc)},
        )
