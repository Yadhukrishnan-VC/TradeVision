from __future__ import annotations

from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheck,
    RiskCheckContext,
    RiskCheckResult,
)
from apps.risk_management.domain.value_objects import RejectionReason


class MarketSessionCheck(RiskCheck):
    """Fail closed when evaluation occurs outside NSE market hours."""

    @property
    def check_id(self) -> str:
        return "market_session_v1"

    @property
    def reason(self) -> RejectionReason:
        return RejectionReason.MARKET_CLOSED

    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        if not ctx.is_market_open:
            return RiskCheckResult(
                reason=RejectionReason.MARKET_CLOSED,
                message="Evaluation outside NSE market hours / trading day",
            )
        return None
