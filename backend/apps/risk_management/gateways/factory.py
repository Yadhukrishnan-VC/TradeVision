from __future__ import annotations

import uuid

from django.conf import settings

from apps.risk_management.application.ports import (
    CapitalGateway,
    PortfolioStateGateway,
)


def _gateway_impl() -> str:
    """Return the configured gateway implementation (defaults to "stub").

    The production default lives in ``settings.RISK_MANAGEMENT_GATEWAY_IMPL``
    ("portfolio" — ADR-028 DoD #7); this defensive fallback only triggers when
    the setting is absent entirely.
    """
    return getattr(settings, "RISK_MANAGEMENT_GATEWAY_IMPL", "stub")


def get_capital_gateway(account_id: uuid.UUID | None = None) -> CapitalGateway:
    """Return the :class:`CapitalGateway` for the configured implementation.

    ADR-028 §2.9: swaps the M3 config-driven stub for the real
    ``apps.portfolio`` capital source without touching the port contract.

    ``account_id`` optionally pins the gateway to one account (backtest
    replay); ``None`` preserves the production ``is_default`` resolution.
    """
    if _gateway_impl() == "portfolio":
        from apps.portfolio.gateways.real_capital_gateway import RealCapitalGateway

        return RealCapitalGateway(account_id=account_id)
    from apps.risk_management.gateways.stub_portfolio_state_gateway import (
        StubPortfolioStateGateway,
    )

    return StubPortfolioStateGateway()


def get_portfolio_state_gateway(account_id: uuid.UUID | None = None) -> PortfolioStateGateway:
    """Return the :class:`PortfolioStateGateway` for the configured impl.

    ``account_id`` optionally pins the gateway to one account (backtest
    replay); ``None`` preserves the production ``is_default`` resolution.
    """
    if _gateway_impl() == "portfolio":
        from apps.portfolio.gateways.real_portfolio_state_gateway import (
            RealPortfolioStateGateway,
        )

        return RealPortfolioStateGateway(account_id=account_id)
    from apps.risk_management.gateways.stub_portfolio_state_gateway import (
        StubPortfolioStateGateway,
    )

    return StubPortfolioStateGateway()
