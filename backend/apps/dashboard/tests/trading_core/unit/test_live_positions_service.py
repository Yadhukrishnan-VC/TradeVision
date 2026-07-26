from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from apps.dashboard.application.trading_core.services.live_positions_service import (
    LivePositionsService,
)


class TestLivePositionsService:
    def test_list_open_returns_dtos(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_price = MagicMock()

        mock_position = MagicMock()
        mock_position.position_id = uuid4()
        mock_position.account_id = account_id
        mock_position.symbol = "RELIANCE"
        mock_position.side = "LONG"
        mock_position.quantity = Decimal("100")
        mock_position.entry_price = Decimal("2500.00")
        mock_position.is_open = True
        mock_position.opened_at = None
        mock_position.closed_at = None

        mock_repo.list_open.return_value = [mock_position]
        mock_price.get_price.return_value = Decimal("2600.00")

        service = LivePositionsService(repository=mock_repo, price_cache=mock_price)
        dtos = service.list_open(account_id)

        assert len(dtos) == 1
        assert dtos[0].symbol == "RELIANCE"
        assert dtos[0].current_price == Decimal("2600.00")
        assert dtos[0].unrealized_pnl == Decimal("10000.00")

    def test_list_open_no_price(self) -> None:
        account_id = uuid4()
        mock_repo = MagicMock()
        mock_price = MagicMock()

        mock_position = MagicMock()
        mock_position.position_id = uuid4()
        mock_position.account_id = account_id
        mock_position.symbol = "RELIANCE"
        mock_position.side = "LONG"
        mock_position.quantity = Decimal("100")
        mock_position.entry_price = Decimal("2500.00")
        mock_position.is_open = True
        mock_position.opened_at = None
        mock_position.closed_at = None

        mock_repo.list_open.return_value = [mock_position]
        mock_price.get_price.return_value = None

        service = LivePositionsService(repository=mock_repo, price_cache=mock_price)
        dtos = service.list_open(account_id)

        assert dtos[0].current_price is None
        assert dtos[0].unrealized_pnl is None

    def test_get_returns_dto(self) -> None:
        account_id = uuid4()
        position_id = uuid4()
        mock_repo = MagicMock()
        mock_price = MagicMock()

        mock_position = MagicMock()
        mock_position.position_id = position_id
        mock_position.account_id = account_id
        mock_position.symbol = "RELIANCE"
        mock_position.side = "SHORT"
        mock_position.quantity = Decimal("100")
        mock_position.entry_price = Decimal("2500.00")
        mock_position.is_open = True
        mock_position.opened_at = None
        mock_position.closed_at = None

        mock_repo.get.return_value = mock_position
        mock_price.get_price.return_value = Decimal("2400.00")

        service = LivePositionsService(repository=mock_repo, price_cache=mock_price)
        dto = service.get(account_id, position_id)

        assert dto.side == "SHORT"
        assert dto.unrealized_pnl == Decimal("10000.00")

    def test_get_raises_not_found(self) -> None:
        from apps.dashboard.domain.trading_core.exceptions import PositionNotFound

        account_id = uuid4()
        position_id = uuid4()
        mock_repo = MagicMock()
        mock_price = MagicMock()
        mock_repo.get.side_effect = PositionNotFound(
            message="Not found", code="position_not_found"
        )

        service = LivePositionsService(repository=mock_repo, price_cache=mock_price)
        with pytest.raises(PositionNotFound):
            service.get(account_id, position_id)
