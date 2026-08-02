from __future__ import annotations

import logging
from decimal import Decimal

from apps.risk_management.application.risk_config import risk_config_from_settings

logger = logging.getLogger(__name__)


class StubPortfolioStateGateway:
    """Config-driven capital/exposure source for M3.

    Implements the :class:`CapitalGateway` and :class:`PortfolioStateGateway`
    protocols using ``settings.RISK_MANAGEMENT`` values.

    GUARDRAIL (ADR-027): this is a data source for risk *evaluation* only —
    it never backs a real order. Every read logs a structured ``WARNING`` and
    every persisted :class:`RiskDecision` records ``implementation_name`` so
    any downstream misuse of stub data is auditable.
    """

    implementation_name = "stub"

    def __init__(self) -> None:
        self._config = risk_config_from_settings()

    # ------------------------------------------------------------------
    # CapitalGateway
    # ------------------------------------------------------------------

    def get_available_capital(self) -> Decimal | None:
        self._log_warning("get_available_capital")
        return self._config.available_capital

    def get_max_position_size(self) -> int:
        self._log_warning("get_max_position_size")
        return self._config.max_position_size

    # ------------------------------------------------------------------
    # PortfolioStateGateway
    # ------------------------------------------------------------------

    def get_current_exposure(self) -> Decimal:
        self._log_warning("get_current_exposure")
        return self._config.current_exposure

    def get_daily_loss(self) -> Decimal:
        self._log_warning("get_daily_loss")
        return self._config.daily_loss

    def get_instrument_max_qty(self, symbol: str) -> int | None:
        self._log_warning("get_instrument_max_qty")
        return self._config.instrument_max_qty

    def get_tradable_symbols(self) -> frozenset[str]:
        return self._config.tradable_symbols

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _log_warning(self, method: str) -> None:
        logger.warning(
            "non_production_capital_source",
            extra={
                "gateway": self.implementation_name,
                "method": method,
                "hint": "stub capital data — never used to back a real order",
            },
        )
