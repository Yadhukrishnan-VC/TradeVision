from __future__ import annotations

import logging
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone

from apps.risk_management.domain.entities import RiskDecision
from apps.risk_management.infrastructure.models import (
    KillSwitchState,
    RiskDecisionExecution,
)
from core.repository import BaseRepository

logger = logging.getLogger(__name__)


class RiskDecisionRepository(BaseRepository[RiskDecisionExecution]):
    def get_by_id(self, entity_id: uuid.UUID) -> RiskDecisionExecution | None:
        try:
            return RiskDecisionExecution.objects.get(id=entity_id)
        except RiskDecisionExecution.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[RiskDecisionExecution]:
        return list(RiskDecisionExecution.objects.filter(**filters))

    def create(self, entity: RiskDecisionExecution) -> RiskDecisionExecution:
        entity.full_clean()
        entity.save()
        return entity

    def create_from_decision(
        self, decision: RiskDecision, analysis_event_id: str
    ) -> RiskDecisionExecution | None:
        """Persist a decision, returning ``None`` on duplicate delivery.

        Mirrors ``rule_engine``'s idempotent ``create_from_firing``: the
        (analysis_event_id, rule_id) UniqueConstraint is enforced first by
        ``full_clean`` and then by the database; both surfaces are caught and
        treated as a duplicate rather than an error.
        """
        try:
            execution = RiskDecisionExecution(
                analysis_event_id=analysis_event_id,
                rule_id=decision.rule_id,
                symbol=decision.symbol,
                event_type=decision.event_type,
                status=decision.status.value,
                rejection_code=(
                    decision.rejection.code.value if decision.rejection else None
                ),
                entry_price=str(decision.entry_price) if decision.entry_price else None,
                stop_loss=str(decision.stop_loss) if decision.stop_loss else None,
                position_size=decision.position_size,
                risk_amount=str(decision.risk_amount) if decision.risk_amount else None,
                risk_pct_of_capital=str(decision.risk_pct_of_capital),
                risk_reward_ratio=str(decision.risk_reward_ratio),
                trigger_data=decision.trigger_data,
                reason_message=decision.reason_message,
                portfolio_gateway_impl=decision.portfolio_gateway_impl,
            )
            execution.full_clean()
            execution.save()
            return execution
        except (IntegrityError, ValidationError):
            logger.warning(
                "duplicate_risk_decision",
                extra={
                    "analysis_event_id": analysis_event_id,
                    "rule_id": decision.rule_id,
                    "symbol": decision.symbol,
                },
            )
            return None

    def mark_published(
        self,
        analysis_event_id: uuid.UUID,
        published_event_id: uuid.UUID,
        rule_id: str | None = None,
    ) -> None:
        RiskDecisionExecution.objects.filter(
            analysis_event_id=analysis_event_id,
            rule_id=rule_id,
            published_event_id__isnull=True,
        ).update(published_event_id=published_event_id)

    def update(self, entity: RiskDecisionExecution) -> RiskDecisionExecution:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        RiskDecisionExecution.objects.filter(id=entity_id).delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return RiskDecisionExecution.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return RiskDecisionExecution.objects.filter(**filters).count()


class KillSwitchStateRepository(BaseRepository[KillSwitchState]):
    def get_by_id(self, entity_id: uuid.UUID) -> KillSwitchState | None:
        try:
            return KillSwitchState.objects.get(id=entity_id)
        except KillSwitchState.DoesNotExist:
            return None

    def get_active(self, scope: str, symbol: str | None = None) -> KillSwitchState | None:
        try:
            return KillSwitchState.objects.get(
                scope=scope,
                symbol=symbol,
                is_active=True,
            )
        except KillSwitchState.DoesNotExist:
            return None

    def has_active(self, scope: str, symbol: str | None = None) -> bool:
        return KillSwitchState.objects.filter(
            scope=scope,
            symbol=symbol,
            is_active=True,
        ).exists()

    def list(self, **filters: Any) -> list[KillSwitchState]:
        return list(KillSwitchState.objects.filter(**filters))

    def create(self, entity: KillSwitchState) -> KillSwitchState:
        entity.full_clean()
        entity.save()
        return entity

    def deactivate_all_for_scope_symbol(
        self, scope: str, symbol: str | None
    ) -> int:
        return KillSwitchState.objects.filter(
            scope=scope,
            symbol=symbol,
            is_active=True,
        ).update(is_active=False, deactivated_at=timezone.now())

    def update(self, entity: KillSwitchState) -> KillSwitchState:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        KillSwitchState.objects.filter(id=entity_id).delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return KillSwitchState.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return KillSwitchState.objects.filter(**filters).count()
