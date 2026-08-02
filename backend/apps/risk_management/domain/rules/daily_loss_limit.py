from __future__ import annotations

from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheck,
    RiskCheckContext,
    RiskCheckResult,
)
from apps.risk_management.domain.value_objects import RejectionReason


class DailyLossLimitCheck(RiskCheck):
    """Reject when the daily loss limit is breached.

    Uses realized (+ unrealized, when available) daily loss reported by the
    gateway. When no limit is configured the check passes.
    """

    @property
    def check_id(self) -> str:
        return "daily_loss_limit_v1"

    @property
    def reason(self) -> RejectionReason:
        return RejectionReason.DAILY_LOSS_LIMIT_EXCEEDED

    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        if ctx.daily_loss_limit is None:
            return None
        if ctx.daily_loss >= ctx.daily_loss_limit:
            return RiskCheckResult(
                reason=self.reason,
                message=(
                    f"Daily loss {ctx.daily_loss} >= limit {ctx.daily_loss_limit}"
                ),
            )
        return None
