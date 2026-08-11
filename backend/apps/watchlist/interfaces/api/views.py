from __future__ import annotations

import uuid
from typing import Any

from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.domain.value_objects import Symbol
from apps.watchlist.application.services import WatchlistService
from apps.watchlist.domain.exceptions import (
    InstrumentNotFoundError,
    WatchlistEntryNotFoundError,
)
from apps.watchlist.infrastructure.quote_source import MarketDataQuoteLookup
from apps.watchlist.interfaces.api.permissions import (
    HasManageWatchlist,
    HasReadWatchlist,
    IsWatchlistAccountOwner,
)
from apps.watchlist.interfaces.api.serializers import (
    WatchlistAddSerializer,
    WatchlistEntrySerializer,
    WatchlistReorderSerializer,
)


def _problem_detail(
    exc_type: str, title: str, status_code: int, instance: str
) -> dict[str, Any]:
    return {
        "type": f"urn:tradevision:error:{exc_type}",
        "title": title,
        "status": status_code,
        "instance": instance,
    }


class WatchlistListView(GenericAPIView):
    """List or add watchlist entries for an account (WATCH-1).

    GET  /api/v1/watchlist/?account_id=<uuid>   → 200 enriched list
    POST /api/v1/watchlist/                     → 201 created / 200 present
    """

    serializer_class = WatchlistAddSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = WatchlistService()
        self._quote_lookup = MarketDataQuoteLookup()

    def get_permissions(self):
        base = [IsWatchlistAccountOwner()]
        if self.request.method == "POST":
            return [HasManageWatchlist(), *base]
        return [HasReadWatchlist(), *base]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        account_id = request.query_params.get("account_id")
        if account_id is None:
            return Response(
                _problem_detail(
                    "missing-account-id",
                    "account_id query parameter is required",
                    status.HTTP_400_BAD_REQUEST,
                    request.path,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        entries = self._service.list(account_id)
        rows = [self._enrich(entry) for entry in entries]
        serializer = WatchlistEntrySerializer(rows, many=True)
        return Response(serializer.data)

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            entry, created = self._service.add(
                account_id=data["account_id"],
                instrument_token=data["instrument_token"],
                note=data.get("note", ""),
            )
        except InstrumentNotFoundError as exc:
            return Response(
                _problem_detail(
                    "instrument-not-found",
                    str(exc),
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "id": str(entry.id),
                "account_id": str(entry.account_id),
                "instrument_token": entry.instrument_id,
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def _enrich(self, entry) -> dict[str, Any]:
        symbol = Symbol(
            exchange=entry.instrument.exchange,
            tradingsymbol=entry.instrument.tradingsymbol,
        )
        latest_price = self._quote_lookup.get_latest_price(symbol)
        return {
            "id": entry.id,
            "account_id": entry.account_id,
            "instrument_token": entry.instrument_id,
            "exchange": entry.instrument.exchange,
            "tradingsymbol": entry.instrument.tradingsymbol,
            "name": entry.instrument.name,
            "note": entry.note,
            "sort_order": entry.sort_order,
            "latest_price": latest_price,
            "price_stale": latest_price is None,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
        }


class WatchlistItemView(GenericAPIView):
    """Remove an instrument from an account's watchlist (WATCH-1).

    DELETE /api/v1/watchlist/{instrument_token}/?account_id=<uuid> → 204
    """

    permission_classes = [IsWatchlistAccountOwner, HasManageWatchlist]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = WatchlistService()

    def delete(self, request: Request, instrument_token: int, *args: Any, **kwargs: Any) -> Response:
        account_id = request.query_params.get("account_id")
        if account_id is None:
            return Response(
                _problem_detail(
                    "missing-account-id",
                    "account_id query parameter is required",
                    status.HTTP_400_BAD_REQUEST,
                    request.path,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )
        self._service.remove(account_id, instrument_token)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WatchlistReorderView(GenericAPIView):
    """Apply a new display order to an account's watchlist (WATCH-1).

    PATCH /api/v1/watchlist/reorder/ {account_id, instrument_tokens} → 200
    """

    permission_classes = [IsWatchlistAccountOwner, HasManageWatchlist]
    serializer_class = WatchlistReorderSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._service = WatchlistService()

    def patch(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            self._service.reorder(
                account_id=data["account_id"],
                ordered_tokens=data["instrument_tokens"],
            )
        except WatchlistEntryNotFoundError as exc:
            return Response(
                _problem_detail(
                    "watchlist-entry-not-found",
                    str(exc),
                    status.HTTP_400_BAD_REQUEST,
                    request.path,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "account_id": str(data["account_id"]),
                "instrument_tokens": data["instrument_tokens"],
            }
        )
