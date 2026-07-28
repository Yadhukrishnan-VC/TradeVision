from __future__ import annotations

import uuid
from typing import Any

from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.rule_engine.application.rule_config_query_service import RuleConfigQueryService
from apps.rule_engine.domain.exceptions import RuleConfigNotFound
from apps.rule_engine.infrastructure.models import RuleConfig
from apps.rule_engine.infrastructure.repositories import RuleConfigRepository
from apps.rule_engine.interfaces.api.serializers import (
    RuleConfigSerializer,
    RuleConfigUpdateSerializer,
    RuleExecutionSerializer,
)


def _problem_detail(
    exc_type: str, title: str, status_code: int, instance: str
) -> dict[str, Any]:
    return {
        "type": f"urn:tradevision:error:{exc_type}",
        "title": title,
        "status": status_code,
        "instance": instance,
    }


class RuleConfigListView(ListAPIView):
    serializer_class = RuleConfigSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = RuleConfigQueryService()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        enabled_param = request.query_params.get("enabled")
        enabled: bool | None = None
        if enabled_param is not None:
            enabled = enabled_param.lower() in ("true", "1", "yes")
        configs = self._service.list_configs(enabled=enabled)
        serializer = self.get_serializer(configs, many=True)
        return Response(serializer.data)


class RuleConfigDetailView(GenericAPIView):
    serializer_class = RuleConfigSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = RuleConfigQueryService()

    def get(self, request: Request, rule_id: str, *args: Any, **kwargs: Any) -> Response:
        try:
            config = self._service.get_config(rule_id)
        except RuleConfigNotFound:
            return Response(
                _problem_detail(
                    "rule-config-not-found",
                    f"Rule config {rule_id} not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(config)
        return Response(serializer.data)

    def patch(self, request: Request, rule_id: str, *args: Any, **kwargs: Any) -> Response:
        update_serializer = RuleConfigUpdateSerializer(data=request.data)
        update_serializer.is_valid(raise_exception=True)

        repo = RuleConfigRepository()
        config = repo.get_by_rule_id(rule_id)
        if config is None:
            return Response(
                _problem_detail(
                    "rule-config-not-found",
                    f"Rule config {rule_id} not found",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        for attr, value in update_serializer.validated_data.items():
            setattr(config, attr, value)
        repo.update(config)

        serializer = self.get_serializer(config)
        return Response(serializer.data)


class RuleExecutionListView(ListAPIView):
    serializer_class = RuleExecutionSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = RuleConfigQueryService()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        rule_id = request.query_params.get("rule_id")
        symbol = request.query_params.get("symbol")
        executions = self._service.list_executions(
            rule_id=rule_id,
            symbol=symbol,
        )
        serializer = self.get_serializer(executions, many=True)
        return Response(serializer.data)
