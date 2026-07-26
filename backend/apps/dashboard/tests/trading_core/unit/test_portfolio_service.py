from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from apps.dashboard.application.trading_core.services.portfolio_service import PortfolioService


class TestPortfolioService:
    def test_get_composition_returns_dto(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_price = MagicMock()

        mock_holding = MagicMock()
        mock_holding.account_id = account_id
        mock_holding.symbol = "RELIANCE"
        mock_holding.quantity = Decimal("100")
        mock_holding.avg_cost = Decimal("2500.00")
        mock_holding.cost_basis = Decimal("250000.00")
        mock_holding.opened_at = None

        mock_repo.list_active.return_value = [mock_holding]
        mock_price.get_price.return_value = Decimal("2600.00")

        service = PortfolioService(repository=mock_repo, price_cache=mock_price)
        composition = service.get_composition(account_id)

        assert composition.account_id == account_id
        assert len(composition.holdings) == 1
        assert composition.holdings[0].symbol == "RELIANCE"
        assert composition.holdings[0].market_value == Decimal("260000.00")

    def test_get_composition_no_price(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_price = MagicMock()

        mock_holding = MagicMock()
        mock_holding.account_id = account_id
        mock_holding.symbol = "RELIANCE"
        mock_holding.quantity = Decimal("100")
        mock_holding.avg_cost = Decimal("2500.00")
        mock_holding.cost_basis = Decimal("250000.00")
        mock_holding.opened_at = None

        mock_repo.list_active.return_value = [mock_holding]
        mock_price.get_price.return_value = None

        service = PortfolioService(repository=mock_repo, price_cache=mock_price)
        composition = service.get_composition(account_id)

        assert composition.total_market_value == Decimal("0")
        assert composition.holdings[0].market_value is None

    def test_get_holding_detail(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_price = MagicMock()

        mock_holding = MagicMock()
        mock_holding.account_id = account_id
        mock_holding.symbol = "RELIANCE"
        mock_holding.quantity = Decimal("100")
        mock_holding.avg_cost = Decimal("2500.00")
        mock_holding.cost_basis = Decimal("250000.00")
        mock_holding.opened_at = None

        mock_repo.get.return_value = mock_holding
        mock_price.get_price.return_value = Decimal("2600.00")

        service = PortfolioService(repository=mock_repo, price_cache=mock_price)
        dto = service.get_holding_detail(account_id, "RELIANCE")

        assert dto.symbol == "RELIANCE"
        assert dto.market_value == Decimal("260000.00")
        assert dto.unrealized_pnl == Decimal("10000.00")

    def test_get_composition_empty(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_price = MagicMock()
        mock_repo.list_active.return_value = []

        service = PortfolioService(repository=mock_repo, price_cache=mock_price)
        composition = service.get_composition(account_id)

        assert len(composition.holdings) == 0
        assert composition.total_market_value == Decimal("0")
