from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.portfolio.application.position_ledger_service import PositionLedgerService
from apps.portfolio.application.portfolio_query_service import PortfolioQueryService
from apps.portfolio.domain.exceptions import PortfolioDomainError
from apps.portfolio.domain.value_objects import Side
from apps.portfolio.interfaces.api.permissions import HasManageExecution, HasReadPortfolio
from apps.portfolio.interfaces.api.serializers import (
    AccountCapitalSerializer,
    FillRequestSerializer,
    PositionSerializer,
)


def _fmt(value: Decimal) -> str:
    """Render a Decimal in its natural form (no trailing zeroes)."""
    return format(value.normalize(), "f")


def _problem_detail(
    exc_type: str, title: str, status_code: int, instance: str
) -> dict[str, Any]:
    return {
        "type": f"urn:tradevision:error:{exc_type}",
        "title": title,
        "status": status_code,
        "instance": instance,
    }


def _resolve_primary_account_id() -> uuid.UUID | None:
    """Single-account resolution shared by the read endpoints (ADR-028 §2.8)."""
    from apps.accounts.infrastructure.models import Account

    account = Account.objects.filter(is_default=True).order_by("-created_at").first()
    return account.id if account is not None else None


class PortfolioSummaryView(ListAPIView):
    """Authoritative capital state for the primary account (READ_PORTFOLIO)."""

    permission_classes = [HasReadPortfolio]
    serializer_class = AccountCapitalSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._queries = PortfolioQueryService()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        account_id = _resolve_primary_account_id()
        if account_id is None:
            return Response(
                _problem_detail(
                    "no-primary-account",
                    "No default account configured",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        self._queries.reconcile_unrealized(account_id)
        capital = self._queries.get_account_capital(account_id)
        serializer = self.get_serializer(capital)
        return Response(serializer.data)


class PositionsListView(ListAPIView):
    """Open positions with live price / unrealized / exposure (READ_PORTFOLIO)."""

    permission_classes = [HasReadPortfolio]
    serializer_class = PositionSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._queries = PortfolioQueryService()

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        account_id = _resolve_primary_account_id()
        if account_id is None:
            return Response(
                _problem_detail(
                    "no-primary-account",
                    "No default account configured",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )
        positions = self._queries.get_open_positions(account_id)
        rows = []
        for position in positions:
            current_price = self._queries.get_current_price(position.symbol)
            rows.append(
                {
                    "account_id": position.account_id,
                    "symbol": position.symbol,
                    "side": position.side,
                    "quantity": position.quantity,
                    "avg_entry_price": position.avg_entry_price,
                    "opened_at": position.opened_at,
                    "current_price": current_price,
                    "unrealized_pnl": self._position_unrealized(position),
                    "exposure": (
                        abs(position.quantity)
                        * (current_price or position.avg_entry_price)
                    ),
                }
            )
        serializer = self.get_serializer(rows, many=True)
        return Response(serializer.data)

    def _position_unrealized(self, position) -> Any:
        current_price = self._queries.get_current_price(position.symbol) or position.avg_entry_price
        sign = 1 if position.side.value == "LONG" else -1
        return (current_price - position.avg_entry_price) * position.quantity * sign


class RecordFillView(GenericAPIView):
    """Record a manual/paper fill into the ledger (MANAGE_EXECUTION).

    This is Portfolio's broker-independent entry point for position changes
    (ADR-028 §2.5) — a future broker-sync adapter calls the same
    :class:`PositionLedgerService` instead of getting a parallel path.
    """

    permission_classes = [HasManageExecution]
    serializer_class = FillRequestSerializer

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._ledger = PositionLedgerService()

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        account_id = data.get("account_id") or _resolve_primary_account_id()
        if account_id is None:
            return Response(
                _problem_detail(
                    "no-primary-account",
                    "No default account configured",
                    status.HTTP_404_NOT_FOUND,
                    request.path,
                ),
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            result = self._ledger.record_fill(
                account_id=account_id,
                symbol=data["symbol"],
                side=Side(data["side"]),
                quantity=data["quantity"],
                price=data["price"],
                occurred_at=data.get("occurred_at"),
                source_fill_id=data.get("source_fill_id"),
            )
        except PortfolioDomainError as exc:
            return Response(
                _problem_detail(
                    "invalid-fill",
                    str(exc),
                    status.HTTP_400_BAD_REQUEST,
                    request.path,
                ),
                status=status.HTTP_400_BAD_REQUEST,
            )

        if result is None:
            return Response(
                {
                    "applied": False,
                    "detail": "fill was a duplicate and was skipped",
                }
            )
        return Response(
            {
                "applied": True,
                "position_id": str(result.id),
                "symbol": result.symbol,
                "side": result.side,
                "quantity": _fmt(result.quantity),
            },
            status=status.HTTP_201_CREATED,
        )
