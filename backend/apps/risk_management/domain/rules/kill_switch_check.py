from __future__ import annotations

from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheck,
    RiskCheckContext,
    RiskCheckResult,
)
from apps.risk_management.domain.value_objects import RejectionReason


class KillSwitchCheck(RiskCheck):
    """Fail closed when the global trade-safety kill-switch is active."""

    @property
    def check_id(self) -> str:
        return "kill_switch_v1"

    @property
    def reason(self) -> RejectionReason:
        return RejectionReason.KILL_SWITCH_ACTIVE

    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        if ctx.kill_switch_active:
            return RiskCheckResult(reason=self.reason, message="Global risk kill-switch is active")
        return None
