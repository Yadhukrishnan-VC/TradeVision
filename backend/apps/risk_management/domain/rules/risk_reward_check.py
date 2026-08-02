from __future__ import annotations

from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheck,
    RiskCheckContext,
    RiskCheckResult,
)
from apps.risk_management.domain.value_objects import RejectionReason


class RiskRewardCheck(RiskCheck):
    """Reject when the risk-reward ratio is below the configured floor.

    R:R = |target_price - entry_price| / |entry_price - stop_loss|.
    The check only applies when a target price is available AND a floor is
    configured; otherwise it passes.
    """

    @property
    def check_id(self) -> str:
        return "risk_reward_v1"

    @property
    def reason(self) -> RejectionReason:
        return RejectionReason.RISK_REWARD_BELOW_MINIMUM

    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        if ctx.target_price is None or ctx.min_risk_reward is None:
            return None
        risk_per_unit = abs(ctx.entry_price - ctx.stop_loss)
        if risk_per_unit <= 0:
            return None  # handled by StopDirectionCheck
        rr = abs(ctx.target_price - ctx.entry_price) / risk_per_unit
        if rr < ctx.min_risk_reward:
            return RiskCheckResult(
                reason=self.reason,
                message=f"R:R {rr} below floor {ctx.min_risk_reward}",
            )
        return None
