from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.application.services import APIKeyService
from apps.accounts.domain.value_objects import Scope
from apps.watchlist.application.services import WatchlistService
from apps.watchlist.infrastructure.models import WatchlistEntry

pytestmark = pytest.mark.django_db

WATCHLIST_PATH = "/api/v1/watchlist/"


def _scoped_client(
    api_client: APIClient,
    user: Any,
    scopes: list[Scope],
) -> APIClient:
    api_key, _ = APIKeyService().create_key(user, scopes)
    api_client.force_authenticate(user=user, token=api_key)
    return api_client


@pytest.fixture(autouse=True)
def _fake_quote_prices(monkeypatch) -> None:
    """Resolve quote enrichment deterministically for the API views.

    The views build their own :class:`MarketDataQuoteLookup`; substituting a
    fixed price map keeps the endpoint assertions independent of the
    market-data provider state.
    """
    from apps.watchlist.infrastructure.quote_source import MarketDataQuoteLookup

    prices = {"NSE:RELIANCE": Decimal("2750.50")}

    def get_latest_price(self, symbol) -> Decimal | None:
        return prices.get(symbol.as_broker_string())

    monkeypatch.setattr(MarketDataQuoteLookup, "get_latest_price", get_latest_price)


class TestWatchlistListAPI:
    def test_list_requires_read_scope(self, api_client, user, account) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])

        response = api_client.get(WATCHLIST_PATH, {"account_id": str(account.id)})

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_empty_with_scope(self, api_client, user, account) -> None:
        _scoped_client(api_client, user, [Scope.READ_WATCHLIST])

        response = api_client.get(WATCHLIST_PATH, {"account_id": str(account.id)})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    def test_list_returns_enriched_entries(self, api_client, user, account, instrument) -> None:
        _scoped_client(api_client, user, [Scope.READ_WATCHLIST])
        WatchlistService().add(account.id, instrument.instrument_token, note="watch this")

        response = api_client.get(WATCHLIST_PATH, {"account_id": str(account.id)})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        row = response.data[0]
        assert row["instrument_token"] == instrument.instrument_token
        assert row["exchange"] == "NSE"
        assert row["tradingsymbol"] == "RELIANCE"
        assert row["name"] == "Reliance Industries"
        assert row["note"] == "watch this"
        assert row["sort_order"] == 0
        assert row["latest_price"] == "2750.5"
        assert row["price_stale"] is False

    def test_list_foreign_account_returns_403(
        self, api_client, user, foreign_account
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_WATCHLIST])

        response = api_client.get(WATCHLIST_PATH, {"account_id": str(foreign_account.id)})

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_missing_account_id_returns_400(self, api_client, user) -> None:
        _scoped_client(api_client, user, [Scope.READ_WATCHLIST])

        response = api_client.get(WATCHLIST_PATH)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_degrades_gracefully_when_price_unavailable(
        self, api_client, user, account, instrument, monkeypatch
    ) -> None:
        from apps.watchlist.infrastructure.quote_source import MarketDataQuoteLookup

        _scoped_client(api_client, user, [Scope.READ_WATCHLIST])
        WatchlistService().add(account.id, instrument.instrument_token)

        def get_latest_price(self, symbol) -> Decimal | None:
            return None

        monkeypatch.setattr(MarketDataQuoteLookup, "get_latest_price", get_latest_price)

        response = api_client.get(WATCHLIST_PATH, {"account_id": str(account.id)})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["latest_price"] is None
        assert response.data[0]["price_stale"] is True


class TestWatchlistAddAPI:
    def test_add_requires_manage_scope(self, api_client, user, account, instrument) -> None:
        _scoped_client(api_client, user, [Scope.READ_WATCHLIST])

        response = api_client.post(
            WATCHLIST_PATH,
            {"account_id": str(account.id), "instrument_token": instrument.instrument_token},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_add_creates_entry(self, api_client, user, account, instrument) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])

        response = api_client.post(
            WATCHLIST_PATH,
            {
                "account_id": str(account.id),
                "instrument_token": instrument.instrument_token,
                "note": "favorite",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["created"] is True
        assert response.data["instrument_token"] == instrument.instrument_token
        assert WatchlistEntry.objects.count() == 1

    def test_add_duplicate_returns_200_not_created(
        self, api_client, user, account, instrument
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])
        WatchlistService().add(account.id, instrument.instrument_token)

        response = api_client.post(
            WATCHLIST_PATH,
            {"account_id": str(account.id), "instrument_token": instrument.instrument_token},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["created"] is False
        assert WatchlistEntry.objects.count() == 1

    def test_add_unknown_instrument_returns_404(
        self, api_client, user, account
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])

        response = api_client.post(
            WATCHLIST_PATH,
            {"account_id": str(account.id), "instrument_token": 99999999},
            format="json",
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["type"] == "urn:tradevision:error:instrument-not-found"

    def test_add_foreign_account_returns_403(
        self, api_client, user, foreign_account, instrument
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])

        response = api_client.post(
            WATCHLIST_PATH,
            {
                "account_id": str(foreign_account.id),
                "instrument_token": instrument.instrument_token,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert WatchlistEntry.objects.count() == 0

    def test_add_missing_fields_returns_400(self, api_client, user, account) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])

        response = api_client.post(
            WATCHLIST_PATH, {"account_id": str(account.id)}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_add_controls_character_stripping_at_api(
        self, api_client, user, account, instrument
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])

        response = api_client.post(
            WATCHLIST_PATH,
            {
                "account_id": str(account.id),
                "instrument_token": instrument.instrument_token,
                "note": "ok\u0007strip",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        stored = WatchlistEntry.objects.get(instrument_id=instrument.instrument_token)
        assert stored.note == "okstrip"


class TestWatchlistItemAPI:
    def test_delete_requires_manage_scope(self, api_client, user, account, instrument) -> None:
        _scoped_client(api_client, user, [Scope.READ_WATCHLIST])
        WatchlistService().add(account.id, instrument.instrument_token)

        response = api_client.delete(
            f"{WATCHLIST_PATH}{instrument.instrument_token}/?account_id={account.id}"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_delete_removes_entry(self, api_client, user, account, instrument) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])
        WatchlistService().add(account.id, instrument.instrument_token)

        response = api_client.delete(
            f"{WATCHLIST_PATH}{instrument.instrument_token}/?account_id={account.id}"
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert WatchlistEntry.objects.count() == 0

    def test_delete_nonexistent_entry_returns_204(
        self, api_client, user, account, instrument
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])

        response = api_client.delete(
            f"{WATCHLIST_PATH}{instrument.instrument_token}/?account_id={account.id}"
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_delete_foreign_account_returns_403(
        self, api_client, user, foreign_account, instrument
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])
        WatchlistService().add(foreign_account.id, instrument.instrument_token)

        response = api_client.delete(
            f"{WATCHLIST_PATH}{instrument.instrument_token}/?account_id={foreign_account.id}"
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert WatchlistEntry.objects.count() == 1

    def test_delete_missing_account_id_returns_400(
        self, api_client, user, instrument
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])

        response = api_client.delete(f"{WATCHLIST_PATH}{instrument.instrument_token}/")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestWatchlistReorderAPI:
    def test_reorder_requires_manage_scope(
        self, api_client, user, account, instruments
    ) -> None:
        _scoped_client(api_client, user, [Scope.READ_WATCHLIST])
        service = WatchlistService()
        for inst in instruments:
            service.add(account.id, inst.instrument_token)

        response = api_client.patch(
            f"{WATCHLIST_PATH}reorder/",
            {
                "account_id": str(account.id),
                "instrument_tokens": [inst.instrument_token for inst in instruments],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_reorder_applies_new_order(self, api_client, user, account, instruments) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])
        service = WatchlistService()
        for inst in instruments:
            service.add(account.id, inst.instrument_token)

        tokens = [inst.instrument_token for inst in instruments]
        reversed_tokens = list(reversed(tokens))

        response = api_client.patch(
            f"{WATCHLIST_PATH}reorder/",
            {"account_id": str(account.id), "instrument_tokens": reversed_tokens},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["instrument_tokens"] == reversed_tokens
        assert [e.instrument_id for e in service.list(account.id)] == reversed_tokens

    def test_reorder_unknown_token_rolls_back(
        self, api_client, user, account, instruments
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])
        service = WatchlistService()
        for inst in instruments:
            service.add(account.id, inst.instrument_token)
        before = [e.instrument_id for e in service.list(account.id)]

        response = api_client.patch(
            f"{WATCHLIST_PATH}reorder/",
            {
                "account_id": str(account.id),
                "instrument_tokens": [instruments[2].instrument_token, 99999999, instruments[0].instrument_token],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["type"] == "urn:tradevision:error:watchlist-entry-not-found"
        assert [e.instrument_id for e in service.list(account.id)] == before

    def test_reorder_duplicate_tokens_returns_400(
        self, api_client, user, account, instruments
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])
        service = WatchlistService()
        for inst in instruments:
            service.add(account.id, inst.instrument_token)

        response = api_client.patch(
            f"{WATCHLIST_PATH}reorder/",
            {
                "account_id": str(account.id),
                "instrument_tokens": [
                    instruments[0].instrument_token,
                    instruments[0].instrument_token,
                    instruments[1].instrument_token,
                ],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_reorder_foreign_account_returns_403(
        self, api_client, user, foreign_account, instruments
    ) -> None:
        _scoped_client(api_client, user, [Scope.MANAGE_WATCHLIST])
        service = WatchlistService()
        for inst in instruments:
            service.add(foreign_account.id, inst.instrument_token)

        response = api_client.patch(
            f"{WATCHLIST_PATH}reorder/",
            {
                "account_id": str(foreign_account.id),
                "instrument_tokens": [inst.instrument_token for inst in instruments],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert [e.instrument_id for e in service.list(foreign_account.id)] == [
            inst.instrument_token for inst in instruments
        ]
