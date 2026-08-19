"""
Risk Management — deterministic risk-check base contract.

Mirrors ``core.rules.base_rule`` conventions: each check is a stateless,
pure, I/O-free function of an immutable ``RiskCheckContext``. It either
passes (returns ``None``) or fails closed (returns a ``RiskCheckResult``
carrying an explicit ``RejectionReason``). ``safe_evaluate`` guarantees a
buggy check can never crash the evaluation loop — on error it fails closed
with ``RejectionReason.UNKNOWN``.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from apps.risk_management.domain.value_objects import PortfolioPosition, RejectionReason

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RiskCheckContext:
    """All inputs a risk check may read. Assembled by the evaluation service.

    Every value is pre-fetched upstream (gateway/config/trigger_data) so the
    checks themselves never touch the database or the network.
    """

    symbol: str
    rule_id: str
    event_type: str
    analysis_event_id: UUID
    occurred_at: datetime
    entry_price: Decimal | None = None
    stop_loss: Decimal | None = None
    direction: str = "long"
    target_price: Decimal | None = None
    freshness_validated: bool = True
    is_market_open: bool = True
    kill_switch_active: bool = False
    tradable: bool = True
    risk_pct: Decimal = Decimal("0.01")
    available_capital: Decimal | None = None
    max_position_size: int = 10**6
    current_exposure: Decimal = Decimal(0)
    max_exposure_cap: Decimal | None = None
    daily_loss: Decimal = Decimal(0)
    daily_loss_limit: Decimal | None = None
    min_risk_reward: Decimal | None = None
    instrument_max_qty: int | None = None
    portfolio_gateway_impl: str = "stub"
    """Implementation name of the gateway that produced capital/exposure."""
    proposed_quantity: int | None = None
    """Approved quantity computed by the sizing check; consumed by the
    exposure and R:R checks that run after sizing."""
    portfolio_positions: tuple[PortfolioPosition, ...] = ()
    """Open portfolio positions (sector/notional/trigger-rule) consumed by the
    concentration check. Empty when no positions are open."""
    instrument_sector: str | None = None
    """Sector of the proposed instrument; ``None`` when no sector master data
    exists (the concentration check then fails closed)."""
    max_sector_exposure_pct: Decimal | None = None
    """Configurable cap on same-sector exposure as a share of capital."""
    correlated_trigger_max_multiple: Decimal | None = None
    """Configurable cap on correlated-trigger aggregate exposure as a multiple
    of single-position risk (``capital x risk_pct``)."""


@dataclass(frozen=True)
class RiskCheckResult:
    """Outcome of a single risk check.

    ``reason is None`` means the check passed; a non-None reason means the
    check failed closed. ``position_size`` is populated only by the sizing
    check and carries the approved quantity through to the service.
    """

    reason: RejectionReason | None = None
    message: str = ""
    position_size: int | None = None


class RiskCheck(ABC):
    """Abstract interface for a single deterministic risk check."""

    @property
    @abstractmethod
    def check_id(self) -> str:
        """Stable identifier for this check (e.g. ``kill_switch_v1``)."""

    @abstractmethod
    def evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        """Evaluate the check. Returns ``None`` on pass, a result on fail."""

    @abstractmethod
    def reason(self) -> RejectionReason:
        """The fail-closed reason this check emits when it fails."""

    def safe_evaluate(self, ctx: RiskCheckContext) -> RiskCheckResult | None:
        """Exception-safe wrapper; on error fails closed with UNKNOWN."""
        try:
            return self.evaluate(ctx)
        except Exception:
            logger.exception(
                "risk_check_error",
                extra={"check_id": self.check_id, "symbol": ctx.symbol},
            )
            return RiskCheckResult(
                reason=RejectionReason.UNKNOWN,
                message=f"{self.check_id} raised during evaluation",
            )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(check_id={self.check_id!r})"
