from __future__ import annotations

import uuid

from core.events.event_types import EnrichedIntelligencePacket
from django.db import transaction

from core.rules.rule_registry import RuleRegistry
from core.services import BaseService
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.rule_engine.domain.entities import RuleFiring
from apps.rule_engine.domain.exceptions import RuleEvaluationError
from apps.rule_engine.domain.rules import (
    BreakoutRule,
    LongMomentumRule,
    PriceMovementRule,
    ShortSellRule,
    VolatilityBreakoutRule,
    VolumeSpikeRule,
)
from apps.rule_engine.infrastructure.repositories import RuleExecutionRepository


class RuleEvaluationService(BaseService):
    def __init__(self) -> None:
        super().__init__()
        self._repository = RuleExecutionRepository()
        self._registry = RuleRegistry()
        self._register_builtin_rules()

    def _register_builtin_rules(self) -> None:
        self._registry.register(PriceMovementRule())
        self._registry.register(VolumeSpikeRule())
        self._registry.register(BreakoutRule())
        self._registry.register(LongMomentumRule())
        self._registry.register(ShortSellRule())
        self._registry.register(VolatilityBreakoutRule())

    def evaluate_enriched_packet(
        self,
        enriched: EnrichedIntelligencePacket,
        analysis_event_id: uuid.UUID | None = None,
    ) -> list[RuleFiring]:
        packet = enriched.packet
        if not packet.freshness_validated:
            self._logger.info("packet_not_fresh", extra={"symbol": packet.symbol})
            return []

        results = self._registry.evaluate_all(packet)
        firings: list[RuleFiring] = []
        with transaction.atomic():
            for result in results:
                analysis_event = result.to_analysis_event(
                    symbol=packet.symbol,
                    packet=packet,
                )
                event_id = analysis_event_id or analysis_event.id
                firing = RuleFiring(
                    rule_id=result.rule_id,
                    event_type=result.event_type.value,
                    severity=result.severity,
                    symbol=packet.symbol,
                    trigger_data=result.trigger_data,
                    analysis_event_id=event_id,
                    occurred_at=analysis_event.timestamp,
                )
                execution = self._repository.create_from_firing(firing, str(event_id))
                if execution is None:
                    continue
                firings.append(firing)

        return firings

    def publish_rule_firing(
        self,
        firing: RuleFiring,
        account_id: uuid.UUID | None = None,
    ) -> uuid.UUID | None:
        payload = {
            "symbol": firing.symbol,
            "event_type": firing.event_type,
            "rule_id": firing.rule_id,
            "severity": firing.severity.value,
            "trigger_data": firing.trigger_data,
            "analysis_event_id": str(firing.analysis_event_id),
            "occurred_at": firing.occurred_at.isoformat(),
        }
        # Backtest replay routes the whole chain to an isolated account via an
        # optional, additive payload field; absent -> production is_default
        # resolution downstream (zero behavior change).
        if account_id is not None:
            payload["account_id"] = str(account_id)
        event = DomainEvent.create(
            event_type="rule_engine.RuleFired",
            payload=payload,
            correlation_id=firing.analysis_event_id,
        )
        try:
            bus = get_event_bus()
            bus.publish(event)
            self._repository.mark_published(
                firing.analysis_event_id, event.event_id, rule_id=firing.rule_id
            )
            return event.event_id
        except Exception as exc:
            self._logger.exception(
                "Failed to publish RuleFired event",
                extra={"rule_id": firing.rule_id, "symbol": firing.symbol},
            )
            raise RuleEvaluationError(f"Publish failed: {exc}") from exc
