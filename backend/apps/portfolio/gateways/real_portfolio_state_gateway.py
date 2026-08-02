from __future__ import annotations

import uuid
from decimal import Decimal

from apps.portfolio.application.portfolio_query_service import PortfolioQueryService
from apps.risk_management.application.risk_config import risk_config_from_settings


class RealPortfolioStateGateway:
    """Production :class:`PortfolioStateGateway` backed by ``apps.portfolio``.

    Implements ``apps.risk_management.application.ports.PortfolioStateGateway``
    verbatim (ADR-028 §2.8). Single-account resolution per ADR-028 §2.8 and
    §29: answers for one primary account (``is_default=True``), or an
    explicitly pinned ``account_id``.

    ``get_instrument_max_qty`` / ``get_tradable_symbols`` stay config-driven
    (``settings.RISK_MANAGEMENT``) because no instrument-master table exists
    yet — flagged in ADR-028 §11/§29, not silently assumed.
    """

    implementation_name = "portfolio_v1"

    def __init__(
        self,
        query_service: PortfolioQueryService | None = None,
        account_id: uuid.UUID | None = None,
    ) -> None:
        self._queries = query_service or PortfolioQueryService()
        self._account_id = account_id
        self._config = risk_config_from_settings()

    def get_current_exposure(self) -> Decimal:
        account_id = self._resolve_primary_account_id()
        if account_id is None:
            return Decimal(0)
        return self._queries.get_exposure(account_id)

    def get_daily_loss(self) -> Decimal:
        account_id = self._resolve_primary_account_id()
        if account_id is None:
            return Decimal(0)
        return self._queries.get_daily_loss(account_id)

    def get_instrument_max_qty(self, symbol: str) -> int | None:
        return self._config.instrument_max_qty

    def get_tradable_symbols(self) -> frozenset[str]:
        return self._config.tradable_symbols

    def _resolve_primary_account_id(self) -> uuid.UUID | None:
        """Resolve the single primary account (ADR-028 §2.8, §29 blocker)."""
        if self._account_id is not None:
            return self._account_id
        from apps.accounts.infrastructure.models import Account

        account = Account.objects.filter(is_default=True).order_by("-created_at").first()
        return account.id if account is not None else None
