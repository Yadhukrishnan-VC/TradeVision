from __future__ import annotations

from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheck,
    RiskCheckContext,
    RiskCheckResult,
)
from apps.risk_management.domain.value_objects import RejectionReason


class StopDirectionCheck(RiskCheck):
    """Validate the stop-loss against the setup's entry and direction.

    Fail-closed conditions, in order:
      1. MISSING_STOP_LOSS   — no usable stop_loss in trigger_data.
      2. MISSING_ENTRY_PRICE — no usable entry_price in trigger_data.
      3. STOP_EQUALS_ENTRY   — stop == entry (zero risk distance).
      4. STOP_WRONG_SIDE     — stop on the wrong side of entry for direction.
      5. ZERO_RISK_DISTANCE  — |entry - stop| <= 0.
    """

    @property
    def check_id(self) -> str:
        return "stop_direction_v1"

    @property
    def reason(self) -> RejectionReason:
        return RejectionReason.ZERO_RISK_DISTANCE

    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        if ctx.stop_loss is None or ctx.stop_loss <= 0:
            return RiskCheckResult(
                reason=RejectionReason.MISSING_STOP_LOSS,
                message="No usable stop_loss in trigger_data",
            )
        if ctx.entry_price is None or ctx.entry_price <= 0:
            return RiskCheckResult(
                reason=RejectionReason.MISSING_ENTRY_PRICE,
                message="No usable entry_price in trigger_data",
            )
        if ctx.stop_loss == ctx.entry_price:
            return RiskCheckResult(
                reason=RejectionReason.STOP_EQUALS_ENTRY,
                message="stop_loss equals entry_price",
            )

        if ctx.direction == "long" and ctx.stop_loss > ctx.entry_price:
            return RiskCheckResult(
                reason=RejectionReason.STOP_WRONG_SIDE,
                message="Long stop must sit below entry_price",
            )
        if ctx.direction == "short" and ctx.stop_loss < ctx.entry_price:
            return RiskCheckResult(
                reason=RejectionReason.STOP_WRONG_SIDE,
                message="Short stop must sit above entry_price",
            )
        return None
