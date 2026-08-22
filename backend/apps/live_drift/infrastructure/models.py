"""Owner-flagged observation rules and detected drift alerts.

These models are deliberately NOT ``RuleConfig.validated_regimes``: nothing
here changes what a rule may do with real capital. An :class:`ObservedRule`
row is an explicit, per-(rule, regime[, symbol]) owner opt-in that allows the
rule to fire on the **paper** broker against live data so the drift monitor
has real paper trades to compare against the backtest baseline.
"""

from __future__ import annotations

from django.db import models

from core.models import BaseModel


class ObservedRule(BaseModel):
    """A (rule_id, regime[, symbol]) combo flagged by the owner for live
    paper observation.

    ``baseline_expectancy`` is copied from the edge-validation record when the
    row is flagged (per-trade net P&L expectancy in currency units at
    realistic NSE costs) and is the reference the monitor compares against.
    """

    rule_id = models.CharField(max_length=100)
    regime = models.CharField(max_length=50)
    # Empty string means "any symbol" for this rule/regime pair.
    symbol = models.CharField(max_length=50, blank=True, default="")
    baseline_expectancy = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True,
        help_text="Backtest expectancy per trade at realistic costs, from EDGE_VALIDATION_REPORT_V2.",
    )
    enabled = models.BooleanField(default=True)
    note = models.CharField(max_length=280, blank=True, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rule_id", "regime", "symbol"], name="uniq_observed_rule_scope"
            )
        ]
        indexes = [models.Index(fields=["rule_id", "regime", "enabled"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        scope = self.symbol or "*"
        return f"ObservedRule({self.rule_id}/{self.regime}@{scope} enabled={self.enabled})"


class DriftAlert(BaseModel):
    """One detected divergence between live paper stats and the baseline."""

    observed_rule = models.ForeignKey(
        ObservedRule, on_delete=models.CASCADE, related_name="alerts"
    )
    KIND_SIGN_FLIP = "sign_flip"
    KIND_THRESHOLD = "threshold"
    kind = models.CharField(
        max_length=20,
        choices=[(KIND_SIGN_FLIP, "sign_flip"), (KIND_THRESHOLD, "threshold")],
    )
    window_trades = models.IntegerField()
    live_expectancy = models.DecimalField(max_digits=18, decimal_places=6)
    live_win_rate = models.DecimalField(max_digits=7, decimal_places=4)
    baseline_expectancy = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    message = models.CharField(max_length=500)
    notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["observed_rule", "created_at"])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"DriftAlert({self.observed_rule_id} {self.kind} trades={self.window_trades})"
