from __future__ import annotations

from uuid import UUID

from core.services import BaseService
from apps.rule_engine.domain.exceptions import RuleConfigNotFound
from apps.rule_engine.infrastructure.models import RuleConfig, RuleExecution
from apps.rule_engine.infrastructure.repositories import RuleConfigRepository, RuleExecutionRepository


class RuleConfigQueryService(BaseService):
    def __init__(self) -> None:
        super().__init__()
        self._config_repo = RuleConfigRepository()
        self._execution_repo = RuleExecutionRepository()

    def get_config(self, rule_id: str) -> RuleConfig:
        config = self._config_repo.get_by_rule_id(rule_id)
        if config is None:
            raise RuleConfigNotFound(f"RuleConfig not found for rule_id={rule_id}")
        return config

    def list_configs(self, enabled: bool | None = None) -> list[RuleConfig]:
        filters = {}
        if enabled is not None:
            filters["enabled"] = enabled
        return self._config_repo.list(**filters)

    def get_execution(self, execution_id: UUID) -> RuleExecution | None:
        return self._execution_repo.get_by_id(execution_id)

    def list_executions(
        self,
        rule_id: str | None = None,
        symbol: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[RuleExecution]:
        filters = {}
        if rule_id:
            filters["rule_id"] = rule_id
        if symbol:
            filters["symbol"] = symbol
        all_executions = self._execution_repo.list(**filters)
        return all_executions[offset : offset + limit]
