"""Batch M3.6 — stop-loss exit evaluation.

A ``technical_analysis.TechnicalAnalysisCompleted`` event fires once per bar
in both live REST polling and backtest replay, so this single subscriber
covers both paths with zero backtest-specific code. For the account's open
position on the event's symbol it evaluates the bar's high/low against the
position's stored stop-loss and — if hit — closes the position via the
existing, unmodified ``PositionLedgerService.close_position()``.

Account resolution reuses ``core.execution_context.get_account_override()``
(exactly what ``rule_engine``'s publisher uses to route backtest replay to
its isolated account) and falls back to the same ``is_default``-account
lookup ``ExecutionRequestService`` uses in live mode — no new resolution
logic. When nothing is bound and no default account exists, evaluation is a
safe no-op.

Same-bar ordering is order-independent (Decision B): a position whose
``opened_at`` is at or after the current bar's timestamp is skipped, so a
same-bar re-entry is never stop-closed by the very bar that opened it,
regardless of EventBus handler-dispatch ordering.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.portfolio.application.position_ledger_service import PositionLedgerService
from apps.portfolio.infrastructure.models import Position
from apps.portfolio.infrastructure.repositories import PositionRepository
from core.execution_context import get_account_override
from core.services import BaseService

_SIDE_LONG = "LONG"
_SIDE_SHORT = "SHORT"


def evaluate_stop(
    side: str,
    stop_loss: Decimal,
    bar_high: Decimal,
    bar_low: Decimal,
) -> tuple[bool, Decimal]:
    """Decide whether a bar's high/low breaches a position's stop-loss.

    Gap-through fills at the worse realistic price (Decision A): a LONG exit
    never prices better than ``min(stop_loss, bar_low)`` and a SHORT exit
    never better than ``max(stop_loss, bar_high)``, matching how a real
    stop-market order fills on a gap. Exact equality (``low == stop``) counts
    as a trigger.

    Returns ``(triggered, exit_price)``.
    """
    side_upper = str(side).upper()
    if side_upper == _SIDE_LONG:
        if bar_low <= stop_loss:
            return True, min(stop_loss, bar_low)
        return False, stop_loss
    if side_upper == _SIDE_SHORT:
        if bar_high >= stop_loss:
            return True, max(stop_loss, bar_high)
        return False, stop_loss
    return False, stop_loss


class ExitEvaluationService(BaseService):
    """Orchestrates stop-loss evaluation for one completed-analysis event."""

    def __init__(
        self,
        position_repo: PositionRepository | None = None,
        ledger: PositionLedgerService | None = None,
    ) -> None:
        super().__init__()
        self._positions = position_repo or PositionRepository()
        self._ledger = ledger or PositionLedgerService()

    def evaluate_ta_completed(self, event: DomainEvent) -> Position | None:
        """Evaluate the event's bar against the account's open position.

        Returns the (now closed) ``Position`` when a stop was hit, else
        ``None``. Never raises for routine conditions (no symbol, missing
        price extremes, no position, no stop, same-bar position, unresolved
        account) — those are logged-and-skipped.
        """
        symbol = event.payload.get("symbol")
        if not symbol:
            return None

        price = event.payload.get("price", {}) or {}
        high = self._to_decimal(price.get("high"))
        low = self._to_decimal(price.get("low"))
        if high is None or low is None:
            self._logger.info(
                "exit_skip_missing_extremes",
                extra={"symbol": symbol, "event_id": str(event.event_id)},
            )
            return None

        bar_timestamp = self._bar_timestamp(event)

        account_id = self._resolve_account_id()
        if account_id is None:
            self._logger.info(
                "exit_skip_no_account",
                extra={"symbol": symbol, "event_id": str(event.event_id)},
            )
            return None

        position = self._positions.get_open(account_id, symbol)
        if position is None:
            return None
        if position.stop_loss is None:
            self._logger.info(
                "exit_skip_no_stop",
                extra={
                    "symbol": symbol,
                    "account_id": str(account_id),
                    "position_id": str(position.id),
                },
            )
            return None
        if bar_timestamp is not None and position.opened_at >= bar_timestamp:
            self._logger.info(
                "exit_skip_same_bar_position",
                extra={
                    "symbol": symbol,
                    "account_id": str(account_id),
                    "position_id": str(position.id),
                },
            )
            return None

        triggered, exit_price = evaluate_stop(
            position.side, position.stop_loss, high, low
        )
        if not triggered:
            return None

        self._ledger.close_position(
            account_id,
            symbol,
            exit_price,
            occurred_at=bar_timestamp,
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
        )
        self._logger.info(
            "position_closed_by_stop",
            extra={
                "symbol": symbol,
                "account_id": str(account_id),
                "position_id": str(position.id),
                "exit_price": str(exit_price),
                "stop_loss": str(position.stop_loss),
                "correlation_id": str(event.correlation_id),
            },
        )
        # ``close_position`` returns ``None`` on a full close (record_fill
        # returns None when it fully closes); return the position that WAS
        # open, so callers can inspect what was closed.
        return position

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_account_id() -> uuid.UUID | None:
        """Reuse the exact account routing every producer already uses.

        ``get_account_override()`` pins the backtest's isolated account;
        outside replay it is ``None`` and evaluation falls back to the same
        ``is_default`` lookup ``ExecutionRequestService`` uses for order
        intake. No new resolution logic.
        """
        from apps.execution.application.execution_request_service import (
            ExecutionRequestService,
        )

        override = get_account_override()
        if override is not None:
            return override
        account = ExecutionRequestService._default_account()
        return account.id if account is not None else None

    @staticmethod
    def _bar_timestamp(event: DomainEvent) -> datetime | None:
        raw = event.payload.get("snapshot_timestamp")
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (TypeError, ValueError):
            return None
