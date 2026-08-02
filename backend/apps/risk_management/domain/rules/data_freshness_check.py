from __future__ import annotations

from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheck,
    RiskCheckContext,
    RiskCheckResult,
)
from apps.risk_management.domain.value_objects import RejectionReason


class DataFreshnessCheck(RiskCheck):
    """Fail closed on stale packet/session facts at fire time."""

    @property
    def check_id(self) -> str:
        return "data_freshness_v1"

    @property
    def reason(self) -> RejectionReason:
        return RejectionReason.STALE_DATA

    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        if not ctx.freshness_validated:
            return RiskCheckResult(
                reason=RejectionReason.STALE_DATA,
                message="Packet/session facts not fresh at fire time",
            )
        return None
