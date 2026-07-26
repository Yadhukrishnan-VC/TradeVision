from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from celery import shared_task

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.ingestion.application.chartink_scan_fetcher import ChartinkScanFetcher
from apps.ingestion.infrastructure.repositories import RawWebhookEventRepository
from apps.common.domain.value_objects import IdempotencyKey

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
    queue="webhooks",
    time_limit=60,
)
def poll_chartink_scans(
    self: Any,
    scan_name: str,
    scan_id: int,
    shared_secret: str | None = None,
) -> dict[str, Any]:
    """Poll Chartink for scan results and publish ``ScanResultReceived``.

    Called by Celery Beat on a schedule. Each scan configuration gets
    its own periodic task entry.

    Args:
        scan_name:     Human-readable scan identifier.
        scan_id:       Chartink numeric scan ID.
        shared_secret: Optional HMAC secret for the X-Signature header.

    Returns:
        The scan result dict with ``scan_name`` and ``symbols``.
    """
    try:
        fetcher = ChartinkScanFetcher(
            scan_name=scan_name,
            scan_id=scan_id,
            shared_secret=shared_secret,
        )
        result = fetcher.fetch()

        event_bus = get_event_bus()
        correlation_id = IdempotencyKey.generate(
            scan_name,
            datetime.now(timezone.utc).strftime("%Y-%m-%d-%H"),
        )

        event = DomainEvent.create(
            event_type="ingestion.ScanResultReceived",
            payload={
                "scan_name": result["scan_name"],
                "symbols": result["symbols"],
                "received_at": result["received_at"],
            },
            correlation_id=uuid.UUID(hex=correlation_id.value[:32]),
            version=1,
        )
        event_bus.publish(event)

        logger.info(
            "chartink_scan_poll_complete",
            extra={
                "scan_name": scan_name,
                "symbol_count": len(result.get("symbols", [])),
            },
        )
        return result
    except Exception as exc:
        logger.error(
            "chartink_scan_poll_failed",
            extra={"scan_name": scan_name, "scan_id": scan_id, "error": str(exc)},
        )
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
    queue="webhooks",
    time_limit=30,
)
def reprocess_unprocessed_webhooks(self: Any) -> int:
    """Re-emit ``ingestion.RawAlertReceived`` for stuck unprocessed events.

    Safety-net task: any ``RawWebhookEvent`` that remains ``processed=False``
    for more than 2 minutes is re-published. Idempotency is guaranteed by
    the deterministic ``correlation_id`` in the downstream consumer.

    Returns:
        Number of events reprocessed.
    """
    try:
        repo = RawWebhookEventRepository()
        unprocessed = repo.find_unprocessed(older_than_minutes=2)
        event_bus = get_event_bus()

        count = 0
        for raw_event in unprocessed:
            source = raw_event.source

            raw_payload = raw_event.raw_body
            if isinstance(raw_payload, str):
                import json
                raw_payload = json.loads(raw_payload)

            alert_id = raw_payload.get("alert_id", str(raw_event.id))
            correlation_source = f"{source}:{alert_id}"

            event = DomainEvent.create(
                event_type="ingestion.RawAlertReceived",
                payload={
                    "raw_payload": raw_payload,
                    "source": source,
                    "received_at": raw_event.received_at.isoformat(),
                    "signature_valid": raw_event.signature_valid,
                },
                correlation_id=uuid.UUID(
                    hex=IdempotencyKey.generate(correlation_source).value[:32],
                ),
                version=1,
            )
            event_bus.publish(event)
            repo.mark_processed(raw_event.id)
            count += 1

        if count:
            logger.info(
                "reprocess_unprocessed_webhooks_complete",
                extra={"reprocessed_count": count},
            )
        return count
    except Exception as exc:
        logger.error(
            "reprocess_unprocessed_webhooks_failed",
            extra={"error": str(exc)},
        )
        raise self.retry(exc=exc)
