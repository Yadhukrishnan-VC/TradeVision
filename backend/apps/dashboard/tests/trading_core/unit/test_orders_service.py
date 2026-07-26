from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from apps.dashboard.application.trading_core.services.orders_service import OrdersService


class TestOrdersService:
    def test_list_returns_dtos(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()

        mock_order = MagicMock()
        mock_order.order_id = uuid4()
        mock_order.account_id = account_id
        mock_order.symbol = "RELIANCE"
        mock_order.side = "LONG"
        mock_order.order_type = "market"
        mock_order.status = "filled"
        mock_order.quantity = Decimal("100")
        mock_order.filled_quantity = Decimal("100")
        mock_order.avg_fill_price = Decimal("2500.00")
        mock_order.limit_price = None
        mock_order.placed_at = None

        mock_repo.list_all.return_value = [mock_order]

        service = OrdersService(repository=mock_repo)
        dtos = service.list(account_id)

        assert len(dtos) == 1
        assert dtos[0].symbol == "RELIANCE"
        assert dtos[0].status == "filled"
        assert dtos[0].avg_fill_price == Decimal("2500.00")

    def test_get_returns_dto(self) -> None:
        account_id = uuid4()
        order_id = uuid4()
        mock_repo = MagicMock()

        mock_order = MagicMock()
        mock_order.order_id = order_id
        mock_order.account_id = account_id
        mock_order.symbol = "RELIANCE"
        mock_order.side = "LONG"
        mock_order.order_type = "limit"
        mock_order.status = "pending"
        mock_order.quantity = Decimal("50")
        mock_order.filled_quantity = Decimal("0")
        mock_order.avg_fill_price = None
        mock_order.limit_price = Decimal("2450.00")
        mock_order.placed_at = None

        mock_repo.get.return_value = mock_order

        service = OrdersService(repository=mock_repo)
        dto = service.get(account_id, order_id)

        assert dto.order_type == "limit"
        assert dto.limit_price == Decimal("2450.00")
        assert dto.quantity == Decimal("50")

    def test_get_raises_not_found(self) -> None:
        from apps.dashboard.domain.trading_core.exceptions import OrderNotFound

        account_id = uuid4()
        order_id = uuid4()
        mock_repo = MagicMock()
        mock_repo.get.side_effect = OrderNotFound(
            message="Not found", code="order_not_found"
        )

        service = OrdersService(repository=mock_repo)
        with pytest.raises(OrderNotFound):
            service.get(account_id, order_id)
