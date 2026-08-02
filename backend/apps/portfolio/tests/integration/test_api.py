from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.application.services import APIKeyService
from apps.accounts.domain.value_objects import Scope
from apps.portfolio.application.capital_service import CapitalService
from apps.portfolio.application.position_ledger_service import PositionLedgerService
from apps.portfolio.application.portfolio_query_service import PortfolioQueryService
from apps.portfolio.domain.value_objects import Side
from apps.portfolio.tests.unit.helpers import FakePriceSource

pytestmark = pytest.mark.django_db

User = get_user_model()

SUMMARY_PATH = "/api/v1/portfolio/"
POSITIONS_PATH = "/api/v1/portfolio/positions/"
FILLS_PATH = "/api/v1/portfolio/fills/"


@pytest.fixture(autouse=True)
def _fake_quote_prices(monkeypatch) -> None:
    """Resolve real-query prices deterministically for the API views.

    The views build their own :class:`PortfolioQueryService` with the
    production price provider; substituting a fixed price map keeps the
    endpoint assertions independent of the market-data DB state.
    """
    from apps.portfolio.infrastructure.price_source import MarketDataCurrentPriceProvider

    prices = {"RELIANCE": Decimal("110.00")}

    def get_current_price(self, symbol: str) -> Decimal | None:
        return prices.get(symbol.upper())

    monkeypatch.setattr(
        MarketDataCurrentPriceProvider, "get_current_price", get_current_price
    )


def _scoped_client(
    api_client: APIClient,
    user: Any,
    scopes: list[Scope],
) -> APIClient:
    api_key, _ = APIKeyService().create_key(user, scopes)
    api_client.force_authenticate(user=user, token=api_key)
    return api_client


class TestPortfolioSummaryAPI:
    def test_summary_requires_scope(self, api_client: APIClient, user: Any) -> None:
        _scoped_client(api_client, user, [Scope.READ_MARKET_DATA])

        response = api_client.get(SUMMARY_PATH)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_summary_404_without_primary_account(
        self, api_client: APIClient, user: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_PORTFOLIO])

        response = api_client.get(SUMMARY_PATH)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["type"] == "urn:tradevision:error:no-primary-account"

    def test_summary_returns_authoritative_capital(
        self, api_client: APIClient, user: Any, account: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_PORTFOLIO])
        CapitalService().deposit(account.id, Decimal("1000000"))

        response = api_client.get(SUMMARY_PATH)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["account_id"] == str(account.id)
        assert response.data["cash"] == "1000000"
        assert response.data["equity"] == "1000000"
        assert response.data["available_capital"] == "1000000"
        assert response.data["margin_used"] == "0"
        assert response.data["realized_pnl_today"] == "0"
        assert response.data["unrealized_pnl_today"] == "0"

    def test_summary_reflects_open_position_margin(
        self, api_client: APIClient, user: Any, account: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_PORTFOLIO])
        CapitalService().deposit(account.id, Decimal("1000000"))
        PositionLedgerService(
            query_service=PortfolioQueryService(
                price_source=FakePriceSource({"RELIANCE": Decimal("110.00")})
            )
        ).record_fill(
            account.id, "RELIANCE", Side.LONG, Decimal("100"), Decimal("100.00")
        )

        response = api_client.get(SUMMARY_PATH)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["margin_used"] == "10000"
        assert response.data["available_capital"] == "990000"
        assert response.data["unrealized_pnl_today"] == "1000"


class TestPositionsListAPI:
    def test_positions_requires_scope(self, api_client: APIClient, user: Any) -> None:
        _scoped_client(api_client, user, [Scope.READ_MARKET_DATA])

        response = api_client.get(POSITIONS_PATH)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_positions_404_without_primary_account(
        self, api_client: APIClient, user: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_PORTFOLIO])

        response = api_client.get(POSITIONS_PATH)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_list_open_positions_with_live_marks(
        self, api_client: APIClient, user: Any, account: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_PORTFOLIO])
        CapitalService().deposit(account.id, Decimal("1000000"))
        PositionLedgerService(
            query_service=PortfolioQueryService(
                price_source=FakePriceSource({"RELIANCE": Decimal("110.00")})
            )
        ).record_fill(
            account.id, "RELIANCE", Side.LONG, Decimal("100"), Decimal("100.00")
        )

        response = api_client.get(POSITIONS_PATH)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        row = response.data[0]
        assert row["symbol"] == "RELIANCE"
        assert row["side"] == "LONG"
        assert row["quantity"] == "100"
        assert row["avg_entry_price"] == "100"
        assert row["current_price"] == "110"
        assert row["unrealized_pnl"] == "1000"
        assert row["exposure"] == "11000"


class TestRecordFillAPI:
    def test_fill_requires_manage_scope(
        self, api_client: APIClient, user: Any, account: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_PORTFOLIO])

        response = api_client.post(
            FILLS_PATH,
            {
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
                "price": "100.00",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_record_fill_creates_position(
        self, api_client: APIClient, user: Any, account: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_PORTFOLIO, Scope.MANAGE_EXECUTION])
        CapitalService().deposit(account.id, Decimal("1000000"))

        response = api_client.post(
            FILLS_PATH,
            {
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "100",
                "price": "100.00",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["applied"] is True
        assert response.data["symbol"] == "RELIANCE"
        assert response.data["side"] == "LONG"
        assert response.data["quantity"] == "100"

        list_response = api_client.get(POSITIONS_PATH)
        assert list_response.status_code == status.HTTP_200_OK
        assert len(list_response.data) == 1

    def test_duplicate_fill_is_skipped(
        self, api_client: APIClient, user: Any, account: Any
    ) -> None:
        import uuid as uuid_mod

        _scoped_client(api_client, user, [Scope.READ_PORTFOLIO, Scope.MANAGE_EXECUTION])
        CapitalService().deposit(account.id, Decimal("1000000"))
        fill_id = str(uuid_mod.uuid4())
        payload = {
            "symbol": "RELIANCE",
            "side": "LONG",
            "quantity": "100",
            "price": "100.00",
            "source_fill_id": fill_id,
        }

        first = api_client.post(FILLS_PATH, payload, format="json")
        second = api_client.post(FILLS_PATH, payload, format="json")

        assert first.status_code == status.HTTP_201_CREATED
        assert second.status_code == status.HTTP_200_OK
        assert second.data["applied"] is False

    def test_invalid_side_rejected(self, api_client: APIClient, user: Any) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_EXECUTION])

        response = api_client.post(
            FILLS_PATH,
            {"symbol": "RELIANCE", "side": "SIDEWAYS", "quantity": "1", "price": "1"},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_insufficient_capital_returns_400(
        self, api_client: APIClient, user: Any, account: Any
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_PORTFOLIO, Scope.MANAGE_EXECUTION])

        response = api_client.post(
            FILLS_PATH,
            {
                "symbol": "RELIANCE",
                "side": "LONG",
                "quantity": "1000",
                "price": "100.00",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["type"] == "urn:tradevision:error:invalid-fill"
