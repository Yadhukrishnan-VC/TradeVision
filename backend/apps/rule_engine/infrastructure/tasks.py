from __future__ import annotations

import logging
import uuid

from celery import shared_task

from core.tasks.base import BaseTask, DEFAULT_MAX_RETRIES, DEFAULT_RETRY_DELAY

logger = logging.getLogger(__name__)


@shared_task(
    name="tradevision.rule_engine.evaluate_packet",
    queue="rule_engine",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def evaluate_packet(
    self,
    enriched: dict,
    analysis_event_id: str | None = None,
) -> list[dict]:
    from core.events.event_types import EnrichedIntelligencePacket
    from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet

    packet = _deserialize_enriched_packet(enriched)
    from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService
    service = RuleEvaluationService()
    firings = service.evaluate_enriched_packet(
        packet,
        analysis_event_id=uuid.UUID(analysis_event_id) if analysis_event_id else None,
    )

    for firing in firings:
        publish_rule_firing.delay(
            rule_id=firing.rule_id,
            event_type=firing.event_type,
            severity=firing.severity.value,
            symbol=firing.symbol,
            trigger_data=firing.trigger_data,
            analysis_event_id=str(firing.analysis_event_id),
            occurred_at=firing.occurred_at.isoformat(),
        )

    return [
        {
            "rule_id": f.rule_id,
            "event_type": f.event_type,
            "severity": f.severity.value,
            "symbol": f.symbol,
        }
        for f in firings
    ]


@shared_task(
    name="tradevision.rule_engine.publish_rule_firing",
    queue="rule_engine",
    bind=True,
    base=BaseTask,
    max_retries=DEFAULT_MAX_RETRIES,
    default_retry_delay=DEFAULT_RETRY_DELAY,
)
def publish_rule_firing(
    self,
    rule_id: str,
    event_type: str,
    severity: str,
    symbol: str,
    trigger_data: dict,
    analysis_event_id: str,
    occurred_at: str,
) -> dict:
    from datetime import datetime
    from core.rules.base_rule import RuleSeverity
    from apps.rule_engine.domain.entities import RuleFiring
    from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

    firing = RuleFiring(
        rule_id=rule_id,
        event_type=event_type,
        severity=RuleSeverity(severity),
        symbol=symbol,
        trigger_data=trigger_data,
        analysis_event_id=uuid.UUID(analysis_event_id),
        occurred_at=datetime.fromisoformat(occurred_at),
    )
    service = RuleEvaluationService()
    published_id = service.publish_rule_firing(firing)
    return {
        "rule_id": rule_id,
        "published_event_id": str(published_id) if published_id else None,
    }
