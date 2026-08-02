from __future__ import annotations

from django.db import models

from core.models import BaseModel


class RiskDecisionExecution(BaseModel):
    """Read-model / audit record of a risk decision outcome.

    Mirrors ``rule_engine.RuleExecution``: one row per evaluated rule firing,
    deduplicated on ``(analysis_event_id, rule_id)``.
    """

    analysis_event_id = models.UUIDField()
    rule_id = models.CharField(max_length=255, db_index=True)
    symbol = models.CharField(max_length=50, db_index=True)
    event_type = models.CharField(max_length=50, default="")
    status = models.CharField(max_length=20, db_index=True)  # APPROVED / REJECTED
    rejection_code = models.CharField(max_length=60, null=True, blank=True)
    entry_price = models.CharField(max_length=40, null=True, blank=True)
    stop_loss = models.CharField(max_length=40, null=True, blank=True)
    position_size = models.IntegerField(default=0)
    risk_amount = models.CharField(max_length=40, null=True, blank=True)
    risk_pct_of_capital = models.CharField(max_length=40, null=True, blank=True)
    risk_reward_ratio = models.CharField(max_length=40, null=True, blank=True)
    trigger_data = models.JSONField(default=dict, blank=True)
    reason_message = models.TextField(default="", blank=True)
    portfolio_gateway_impl = models.CharField(max_length=60, default="stub")
    published_event_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "risk_management_riskdecisionexecution"
        verbose_name = "Risk Decision Execution"
        verbose_name_plural = "Risk Decision Executions"
        constraints = [
            models.UniqueConstraint(
                fields=["analysis_event_id", "rule_id"],
                name="uq_riskdecision_event_rule",
            ),
        ]

    def __str__(self) -> str:
        return f"RiskDecisionExecution({self.status}/{self.rule_id}/{self.analysis_event_id})"


class KillSwitchState(BaseModel):
    """Persistent trade-safety kill-switch state.

    One active row per (scope, symbol) — enforced by the partial unique
    constraint on active rows. Toggles publish
    ``risk_management.KillSwitchActivated`` / ``KillSwitchDeactivated`` events
    which the audit-log ``*`` subscriber records for free.
    """

    scope = models.CharField(max_length=20, db_index=True)  # GLOBAL / ACCOUNT / SYMBOL
    symbol = models.CharField(max_length=50, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    activated_at = models.DateTimeField()
    deactivated_at = models.DateTimeField(null=True, blank=True)
    actor = models.CharField(max_length=255, default="system")
    reason = models.TextField(default="", blank=True)

    class Meta:
        db_table = "risk_management_killswitchstate"
        verbose_name = "Kill Switch State"
        verbose_name_plural = "Kill Switch States"
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "symbol"],
                condition=models.Q(is_active=True),
                name="uq_killswitch_active_scope_symbol",
            ),
        ]

    def __str__(self) -> str:
        return f"KillSwitchState({self.scope}/{self.symbol or '*'} active={self.is_active})"
