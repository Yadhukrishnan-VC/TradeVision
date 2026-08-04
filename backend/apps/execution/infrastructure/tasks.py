from __future__ import annotations

import logging
import uuid

from celery import shared_task

from apps.execution.application.execution_engine import ExecutionEngine
from apps.execution.application.execution_request_service import ExecutionRequestService
from core.tasks.base import DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY, BaseTask

logger = logging.getLogger(__name__)


@shared_task(
    name="tradevision.execution.handle_risk_approved",
    queue="decisions",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def handle_risk_approved(
    self,
    payload: dict,
    correlation_id: str,
    causation_id: str,
    risk_approved_event_id: str,
) -> dict:
    """Ingest a ``risk_management.RiskApproved`` event into the execution app.

    Idempotent on ``risk_approved_event_id``: a redelivered approval is
    skipped (no second ExecutionRequest / Order). Accepted requests chain
    ``process_order`` for broker simulation.
    """
    result = ExecutionRequestService().intake(
        payload=payload,
        correlation_id=uuid.UUID(correlation_id) if correlation_id else uuid.uuid4(),
        causation_id=uuid.UUID(causation_id) if causation_id else None,
        risk_approved_event_id=uuid.UUID(risk_approved_event_id),
    )
    if result.order_id is not None:
        process_order.delay(str(result.order_id), correlation_id=correlation_id)

    logger.info(
        "execution_intake_completed",
        extra={
            "outcome": result.outcome,
            "request_id": str(result.request_id) if result.request_id else "",
            "order_id": str(result.order_id) if result.order_id else "",
            "reason_message": result.reason_message,
        },
    )
    return {
        "outcome": result.outcome,
        "request_id": str(result.request_id) if result.request_id else "",
        "order_id": str(result.order_id) if result.order_id else "",
        "reason_message": result.reason_message,
    }


@shared_task(
    name="tradevision.execution.process_order",
    queue="execution",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def process_order(self, order_id: str, correlation_id: str = "") -> dict:
    """Run one order through the paper broker to fills and the portfolio.

    Idempotent on ``order_id``: terminal orders and already-applied fills are
    skipped, so retries never double-publish or double-fill.
    """
    engine = ExecutionEngine()
    return engine.execute_order(uuid.UUID(order_id))
