from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheck,
    RiskCheckContext,
    RiskCheckResult,
)
from apps.risk_management.domain.value_objects import RejectionReason


class PositionSizingCheck(RiskCheck):
    """Compute the position size from capital, risk fraction and stop distance.

    Formulas (Decimal throughout, never float):
      risk_amount     = capital x risk_pct
      risk_per_unit   = |entry_price - stop_loss|
      raw_size        = floor(risk_amount / risk_per_unit)
      position_size   = min(raw_size, max_position_size,
                            floor(available_capital / entry_price),
                            instrument_max_qty)

    Fail-closed conditions:
      1. MISSING_ACCOUNT_STATE — no capital data from the gateway.
      2. ZERO_CAPITAL          — capital <= 0.
      3. INSUFFICIENT_CAPITAL  — size floors to 0 under the capital constraint.
      4. POSITION_SIZE_ZERO    — size rounds to 0 for any reason.
    """

    @property
    def check_id(self) -> str:
        return "position_sizing_v1"

    @property
    def reason(self) -> RejectionReason:
        return RejectionReason.POSITION_SIZE_ZERO

    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        if ctx.available_capital is None:
            return RiskCheckResult(
                reason=RejectionReason.MISSING_ACCOUNT_STATE,
                message="Gateway returned no capital/exposure data",
            )
        if ctx.available_capital <= 0:
            return RiskCheckResult(
                reason=RejectionReason.ZERO_CAPITAL,
                message=f"Available capital {ctx.available_capital} <= 0",
            )

        risk_amount = ctx.available_capital * ctx.risk_pct
        risk_per_unit = abs(ctx.entry_price - ctx.stop_loss)
        if risk_per_unit <= 0:
            return RiskCheckResult(
                reason=RejectionReason.ZERO_RISK_DISTANCE,
                message="|entry - stop| <= 0",
            )

        raw_size = (risk_amount / risk_per_unit).quantize(
            Decimal(1), rounding=ROUND_FLOOR
        )

        capital_size = (ctx.available_capital / ctx.entry_price).quantize(
            Decimal(1), rounding=ROUND_FLOOR
        )

        caps = [raw_size, Decimal(ctx.max_position_size), capital_size]
        if ctx.instrument_max_qty is not None:
            caps.append(Decimal(ctx.instrument_max_qty))
        size = min(caps)

        if size <= 0:
            if capital_size <= 0:
                return RiskCheckResult(
                    reason=RejectionReason.INSUFFICIENT_CAPITAL,
                    message=(
                        f"Capital {ctx.available_capital} cannot afford "
                        f"1 unit at entry {ctx.entry_price}"
                    ),
                )
            return RiskCheckResult(
                reason=RejectionReason.POSITION_SIZE_ZERO,
                message="Position size rounds to 0",
            )

        return RiskCheckResult(position_size=int(size))
