from __future__ import annotations

from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheck,
    RiskCheckContext,
    RiskCheckResult,
)
from apps.risk_management.domain.value_objects import RejectionReason


class PortfolioConcentrationCheck(RiskCheck):
    """Portfolio-level correlation / concentration risk (fail-closed).

    Governs the *aggregate* footprint of a proposed position against the rest
    of the book, not the single position in isolation:

    - **Same-sector exposure** — the sum of notional across all open positions
      in the proposed instrument's sector, plus the proposed position, must not
      exceed a configurable share of capital
      (``max_sector_exposure_pct``).
    - **Correlated-trigger exposure** — the sum of notional across positions
      fired by the same rule/trigger as the proposed position, plus the
      proposed position, must not exceed a configurable multiple of
      single-position risk (``correlated_trigger_max_multiple`` x
      ``capital x risk_pct``).

    Fail-closed rules (reject rather than assume uncorrelated):

      1. No thresholds configured -> check passes (no concentration governance
         requested).
      2. No capital from the gateway -> :data:`MISSING_ACCOUNT_STATE`.
      3. The proposed instrument has no sector data, any open position has no
         sector data, or no sizing/entry price exists -> the aggregate cannot
         be verified -> :data:`MISSING_SECTOR_DATA`.
      4. When the correlated-trigger threshold is configured, any open position
         without trigger-rule attribution is treated as unverifiable ->
         :data:`MISSING_SECTOR_DATA`.

    Determinism: the check is a pure function of the context; it never touches
    the database or the network (the portfolio gateway pre-fetches positions).
    """

    @property
    def check_id(self) -> str:
        return "portfolio_concentration_v1"

    @property
    def reason(self) -> RejectionReason:
        return RejectionReason.SECTOR_CONCENTRATION_EXCEEDED

    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        if (
            ctx.max_sector_exposure_pct is None
            and ctx.correlated_trigger_max_multiple is None
        ):
            return None

        if ctx.available_capital is None or ctx.available_capital <= 0:
            return RiskCheckResult(
                reason=RejectionReason.MISSING_ACCOUNT_STATE,
                message="Gateway returned no capital; portfolio concentration cannot be assessed",
            )

        if ctx.instrument_sector is None:
            return RiskCheckResult(
                reason=RejectionReason.MISSING_SECTOR_DATA,
                message=f"Sector data unavailable for proposed instrument {ctx.symbol}",
            )

        positions = tuple(ctx.portfolio_positions)
        for position in positions:
            if position.sector is None:
                return RiskCheckResult(
                    reason=RejectionReason.MISSING_SECTOR_DATA,
                    message=(
                        f"Open position {position.symbol} has no sector data; "
                        "same-sector concentration cannot be verified"
                    ),
                )

        if ctx.proposed_quantity is None or ctx.entry_price is None:
            return RiskCheckResult(
                reason=RejectionReason.MISSING_SECTOR_DATA,
                message="Proposed quantity/entry unavailable; portfolio concentration cannot be assessed",
            )

        proposed_notional = ctx.proposed_quantity * ctx.entry_price

        if ctx.max_sector_exposure_pct is not None:
            same_sector = proposed_notional + sum(
                p.notional
                for p in positions
                if p.sector == ctx.instrument_sector
            )
            if same_sector > ctx.max_sector_exposure_pct * ctx.available_capital:
                return RiskCheckResult(
                    reason=RejectionReason.SECTOR_CONCENTRATION_EXCEEDED,
                    message=(
                        f"Same-sector ({ctx.instrument_sector}) exposure "
                        f"{same_sector} exceeds {ctx.max_sector_exposure_pct} "
                        f"of capital {ctx.available_capital}"
                    ),
                )

        if ctx.correlated_trigger_max_multiple is not None:
            for position in positions:
                if position.trigger_rule is None:
                    return RiskCheckResult(
                        reason=RejectionReason.MISSING_SECTOR_DATA,
                        message=(
                            f"Open position {position.symbol} has no trigger-rule "
                            "attribution; correlated exposure cannot be verified"
                        ),
                    )
            correlated = proposed_notional + sum(
                p.notional for p in positions if p.trigger_rule == ctx.rule_id
            )
            single_position_risk = ctx.available_capital * ctx.risk_pct
            if correlated > ctx.correlated_trigger_max_multiple * single_position_risk:
                return RiskCheckResult(
                    reason=RejectionReason.CORRELATED_EXPOSURE_EXCEEDED,
                    message=(
                        f"Correlated-trigger exposure {correlated} exceeds "
                        f"{ctx.correlated_trigger_max_multiple} x single-position "
                        f"risk {single_position_risk}"
                    ),
                )

        return None