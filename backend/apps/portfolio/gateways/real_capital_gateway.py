from __future__ import annotations

import uuid
from decimal import Decimal

from apps.portfolio.application.portfolio_query_service import PortfolioQueryService
from apps.risk_management.application.risk_config import risk_config_from_settings


class RealCapitalGateway:
    """Production :class:`CapitalGateway` backed by ``apps.portfolio``.

    Implements ``apps.risk_management.application.ports.CapitalGateway``
    verbatim (ADR-028 §2.8). Single-account resolution per ADR-028 §2.8: the
    gateway answers for one primary account (``is_default=True``), or an
    explicitly pinned ``account_id``.

    ``implementation_name`` is ``"portfolio_v1"`` so every persisted
    ``RiskDecisionExecution.portfolio_gateway_impl`` proves the decision was
    backed by real capital data, not the stub (ADR-028 §2.8 guardrail).
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

    def get_available_capital(self) -> Decimal | None:
        account_id = self._resolve_primary_account_id()
        if account_id is None:
            return None  # fail-closed: no account -> MISSING_ACCOUNT_STATE
        return self._queries.get_available_capital(account_id)

    def get_max_position_size(self) -> int:
        return self._config.max_position_size

    def _resolve_primary_account_id(self) -> uuid.UUID | None:
        """Resolve the single primary account (ADR-028 §2.8, §29 blocker)."""
        if self._account_id is not None:
            return self._account_id
        from apps.accounts.infrastructure.models import Account

        account = Account.objects.filter(is_default=True).order_by("-created_at").first()
        return account.id if account is not None else None
