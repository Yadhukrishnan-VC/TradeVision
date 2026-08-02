from __future__ import annotations

import logging
import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError

from core.repository import BaseRepository

logger = logging.getLogger(__name__)
from apps.rule_engine.domain.entities import RuleFiring
from apps.rule_engine.infrastructure.models import RuleConfig, RuleExecution


class RuleConfigRepository(BaseRepository[RuleConfig]):
    def get_by_id(self, entity_id: uuid.UUID) -> RuleConfig | None:
        try:
            return RuleConfig.objects.get(id=entity_id)
        except RuleConfig.DoesNotExist:
            return None

    def get_by_rule_id(self, rule_id: str) -> RuleConfig | None:
        try:
            return RuleConfig.objects.get(rule_id=rule_id)
        except RuleConfig.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[RuleConfig]:
        return list(RuleConfig.objects.filter(**filters))

    def create(self, entity: RuleConfig) -> RuleConfig:
        entity.full_clean()
        entity.save()
        return entity

    def update(self, entity: RuleConfig) -> RuleConfig:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        RuleConfig.objects.filter(id=entity_id).delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return RuleConfig.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return RuleConfig.objects.filter(**filters).count()


class RuleExecutionRepository(BaseRepository[RuleExecution]):
    def get_by_id(self, entity_id: uuid.UUID) -> RuleExecution | None:
        try:
            return RuleExecution.objects.get(id=entity_id)
        except RuleExecution.DoesNotExist:
            return None

    def list(self, **filters: Any) -> list[RuleExecution]:
        return list(RuleExecution.objects.filter(**filters))

    def create(self, entity: RuleExecution) -> RuleExecution:
        entity.full_clean()
        entity.save()
        return entity

    def create_from_firing(
        self, firing: RuleFiring, analysis_event_id: str
    ) -> RuleExecution | None:
        try:
            execution = RuleExecution(
                analysis_event_id=analysis_event_id,
                rule_id=firing.rule_id,
                symbol=firing.symbol,
                severity=firing.severity.value,
                trigger_data=firing.trigger_data,
            )
            execution.full_clean()
            execution.save()
            return execution
        except (IntegrityError, ValidationError):
            logger.warning(
                "duplicate_rule_execution",
                extra={
                    "analysis_event_id": analysis_event_id,
                    "rule_id": firing.rule_id,
                    "symbol": firing.symbol,
                },
            )
            return None

    def mark_published(
        self,
        analysis_event_id: uuid.UUID,
        published_event_id: uuid.UUID,
        rule_id: str | None = None,
    ) -> None:
        RuleExecution.objects.filter(
            analysis_event_id=analysis_event_id,
            rule_id=rule_id,
            published_event_id__isnull=True,
        ).update(published_event_id=published_event_id)

    def update(self, entity: RuleExecution) -> RuleExecution:
        entity.full_clean()
        entity.save()
        return entity

    def delete(self, entity_id: uuid.UUID) -> None:
        RuleExecution.objects.filter(id=entity_id).delete()

    def exists(self, entity_id: uuid.UUID) -> bool:
        return RuleExecution.objects.filter(id=entity_id).exists()

    def count(self, **filters: Any) -> int:
        return RuleExecution.objects.filter(**filters).count()
