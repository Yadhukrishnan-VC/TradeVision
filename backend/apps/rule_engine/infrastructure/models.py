from __future__ import annotations

import uuid

from django.db import models

from core.models import BaseModel


class RuleConfig(BaseModel):
    rule_id = models.CharField(max_length=255, unique=True, db_index=True)
    enabled = models.BooleanField(default=True)
    parameters = models.JSONField(default=dict, blank=True)
    severity_override = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Override default severity (LOW, MEDIUM, HIGH, CRITICAL)",
    )
    validated_regimes = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Per-regime go/no-go verdict, keyed by regime name. "
            "Each value: {'status': 'GO'|'NO_GO'|'INSUFFICIENT_DATA', "
            "'expectancy': str, 'profit_factor': str, 'sharpe_ratio': str|None, "
            "'max_drawdown_pct': str, 'trade_count': int, 'backtest_run_id': str, "
            "'evaluated_at': iso8601 str}"
        ),
    )

    class Meta:
        db_table = "rule_engine_ruleconfig"
        verbose_name = "Rule Config"
        verbose_name_plural = "Rule Configs"

    def __str__(self) -> str:
        return f"RuleConfig({self.rule_id}) enabled={self.enabled}"


class RuleExecution(BaseModel):
    analysis_event_id = models.UUIDField()
    rule_id = models.CharField(max_length=255, db_index=True)
    symbol = models.CharField(max_length=50, db_index=True)
    severity = models.CharField(max_length=20)
    trigger_data = models.JSONField(default=dict, blank=True)
    published_event_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "rule_engine_ruleexecution"
        verbose_name = "Rule Execution"
        verbose_name_plural = "Rule Executions"
        constraints = [
            models.UniqueConstraint(
                fields=["analysis_event_id", "rule_id"],
                name="uq_ruleexecution_event_rule",
            ),
        ]

    def __str__(self) -> str:
        return f"RuleExecution({self.rule_id}/{self.analysis_event_id})"
