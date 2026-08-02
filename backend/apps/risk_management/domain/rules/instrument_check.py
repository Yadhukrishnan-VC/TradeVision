from __future__ import annotations

from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheck,
    RiskCheckContext,
    RiskCheckResult,
)
from apps.risk_management.domain.value_objects import RejectionReason


class InstrumentCheck(RiskCheck):
    """Reject when the symbol is not in the configured tradable set.

    The tradable set comes from the portfolio gateway (stub returns a
    config-driven set; empty set means everything is tradable).
    """

    @property
    def check_id(self) -> str:
        return "instrument_v1"

    @property
    def reason(self) -> RejectionReason:
        return RejectionReason.INVALID_INSTRUMENT

    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        if not ctx.tradable:
            return RiskCheckResult(
                reason=self.reason,
                message=f"Symbol {ctx.symbol} not in tradable set",
            )
        return None
