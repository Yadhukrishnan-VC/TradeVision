from __future__ import annotations

from decimal import Decimal

from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheck,
    RiskCheckContext,
    RiskCheckResult,
)
from apps.risk_management.domain.value_objects import RejectionReason


class ExposureLimitCheck(RiskCheck):
    """Reject when the proposed position breaches the portfolio exposure cap.

    Uses the sized ``proposed_quantity x entry_price`` notional against the
    gateway's ``max_exposure_cap``. When no cap is configured the check
    passes (an unset limit is fail-open; M3 configures one by default).
    """

    @property
    def check_id(self) -> str:
        return "exposure_limit_v1"

    @property
    def reason(self) -> RejectionReason:
        return RejectionReason.MAX_EXPOSURE_EXCEEDED

    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        if ctx.max_exposure_cap is None:
            return None
        quantity = Decimal(ctx.proposed_quantity or 0)
        position_notional = ctx.entry_price * quantity
        if ctx.current_exposure + position_notional > ctx.max_exposure_cap:
            return RiskCheckResult(
                reason=self.reason,
                message=(
                    f"Exposure {ctx.current_exposure + position_notional} "
                    f"exceeds cap {ctx.max_exposure_cap}"
                ),
            )
        return None
