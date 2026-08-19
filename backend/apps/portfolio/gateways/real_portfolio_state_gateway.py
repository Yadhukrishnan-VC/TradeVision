from __future__ import annotations

import uuid
from decimal import Decimal

from apps.portfolio.application.portfolio_query_service import PortfolioQueryService
from apps.risk_management.application.risk_config import risk_config_from_settings
from apps.risk_management.domain.value_objects import PortfolioPosition


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

    def get_weekly_loss(self) -> Decimal:
        """Weekly loss — no 7-day P&L ledger exists yet, so ``0`` (never
        trips the weekly breaker against real data; documented gap in the Risk
        Sophistication batch report)."""
        return Decimal(0)

    def get_instrument_max_qty(self, symbol: str) -> int | None:
        return self._config.instrument_max_qty

    def get_tradable_symbols(self) -> frozenset[str]:
        return self._config.tradable_symbols

    def get_portfolio_positions(self) -> tuple[PortfolioPosition, ...]:
        """Open positions as portfolio value objects.

        Notional = ``quantity x avg_entry_price``. ``sector`` and
        ``trigger_rule`` are ``None`` because no sector master or
        position→rule attribution table exists yet — the concentration check
        fails closed when its thresholds are configured (documented in the
        Risk Sophistication batch report), rather than assuming uncorrelated.
        """
        account_id = self._resolve_primary_account_id()
        if account_id is None:
            return ()
        positions = self._queries.get_open_positions(account_id)
        return tuple(
            PortfolioPosition(
                symbol=position.symbol,
                sector=None,
                notional=position.quantity * position.avg_entry_price,
                trigger_rule=None,
            )
            for position in positions
        )

    def get_instrument_sector(self, symbol: str) -> str | None:
        """Sector lookup — no instrument master exists, so always ``None``."""
        return None

    def _resolve_primary_account_id(self) -> uuid.UUID | None:
        """Resolve the single primary account (ADR-028 §2.8, §29 blocker)."""
        if self._account_id is not None:
            return self._account_id
        from apps.accounts.infrastructure.models import Account

        account = Account.objects.filter(is_default=True).order_by("-created_at").first()
        return account.id if account is not None else None
