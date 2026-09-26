"""Deterministic order creation for backtest replay.

The production order path (RuleFired -> AI/oracle -> RiskApproved -> intake)
depends on the external bus / AI chain, which emits no orders in replay.  For
backtests we therefore convert each rule verdict directly into a real ``Order``
under the isolated run account, using the strategy rule's own direction and the
firing trigger data for entry/stop.  Orders are filled by the runner on the
next bar's real open (look-ahead-free), so fill-based stats and the
``StrategySymbolAffinity`` evidence gate use honest prices.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings

from apps.execution.application.execution_request_service import (
    ExecutionRequestService,
)
from apps.portfolio.application.capital_service import CapitalService
from core.execution_context import get_account_override
from core.services import BaseService
from core.logging import get_logger

logger = get_logger(__name__)

# Rules that open short positions.
_SHORT_RULES: frozenset[str] = frozenset({"short_sell_v1", "short_breakdown_v1"})

# Deterministic idempotency namespace for replay-derived approvals.
_REPLAY_NS = uuid.UUID("1b7e4a10-7c22-4f1e-9d3a-6b6f5c2e0a11")

# Candidates used to recover an entry price from firing trigger data.
_ENTRY_KEYS = ("entry_price", "price", "close", "open", "breakout_price")
_STOP_KEYS = ("stop_loss", "stop_price")


class ReplaySignalExecutionService(BaseService):
    """Turn a rule firing into a real order inside a backtest run."""

    def __init__(
        self,
        intake: ExecutionRequestService | None = None,
        capital: CapitalService | None = None,
    ) -> None:
        super().__init__()
        self._intake = intake or ExecutionRequestService()
        self._capital = capital or CapitalService()

    def handle_rule_fired(self, event) -> dict | None:
        """Handle one ``rule_engine.RuleFired`` event during replay.

        Production (no account override) is untouched -- returns ``None`` and
        lets the normal handlers own the event.
        """
        account_override = get_account_override()
        if account_override is None:
            return None

        payload = event.payload or {}
        symbol = str(payload.get("symbol", "")).strip().upper()
        rule_id = str(payload.get("rule_id", "")).strip()
        event_type = str(payload.get("event_type", "")).strip()
        trigger = payload.get("trigger_data") or {}
        if not symbol or not rule_id:
            return None

        entry = self._entry_price(trigger)
        if entry is None or entry <= 0:
            logger.info(
                "replay_order_skipped_no_entry",
                extra={"rule_id": rule_id, "symbol": symbol},
            )
            return None

        direction = "short" if rule_id in _SHORT_RULES else "long"
        stop = self._stop_price(trigger, entry, direction)
        if stop is None or stop <= 0 or stop == entry:
            return None

        account_id = str(account_override)
        if payload.get("account_id"):
            account_id = str(payload["account_id"])

        quantity = self._position_size(account_id, entry, stop)
        if quantity <= 0:
            return None

        approved_payload = {
            "symbol": symbol,
            "rule_id": rule_id,
            "event_type": event_type,
            "direction": direction,
            "entry_price": str(entry),
            "stop_loss": str(stop),
            "position_size": str(quantity),
            "account_id": account_id,
        }
        risk_approved_event_id = uuid.uuid5(
            _REPLAY_NS, f"replay:{event.event_id}"
        )
        result = self._intake.intake(
            payload=approved_payload,
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
            risk_approved_event_id=risk_approved_event_id,
        )
        if result.outcome != "CREATED":
            logger.info(
                "replay_order_result",
                extra={
                    "outcome": result.outcome,
                    "reason": result.reason_message,
                    "rule_id": rule_id,
                    "symbol": symbol,
                },
            )
        return {
            "outcome": result.outcome,
            "order_id": str(result.order_id) if result.order_id else None,
        }

    # ------------------------------------------------------------------
    # Deterministic pricing / sizing
    # ------------------------------------------------------------------

    @staticmethod
    def _as_decimal(value, scale: int = 4) -> Decimal | None:
        try:
            return Decimal(str(value)).quantize(Decimal(1).scaleb(-scale))
        except (InvalidOperation, ArithmeticError, ValueError, TypeError):
            return None

    def _entry_price(self, trigger: dict) -> Decimal | None:
        for key in _ENTRY_KEYS:
            value = self._as_decimal(trigger.get(key))
            if value is not None and value > 0:
                return value
        return None

    def _stop_price(self, trigger: dict, entry: Decimal, direction: str) -> Decimal | None:
        for key in _STOP_KEYS:
            value = self._as_decimal(trigger.get(key))
            if value is not None and value > 0:
                return value
        fallback_pct = Decimal(
            str(getattr(settings, "BACKTEST_STOP_FALLBACK_PCT", "0.02"))
        )
        if direction == "short":
            return (entry * (1 + fallback_pct)).quantize(Decimal("0.01"))
        return (entry * (1 - fallback_pct)).quantize(Decimal("0.01"))

    def _position_size(self, account_id: str, entry: Decimal, stop: Decimal) -> Decimal | None:
        state = self._capital.get_state(uuid.UUID(account_id))
        available = state.available_capital if state is not None else None
        if available is None or available <= 0:
            return None
        risk_pct = Decimal(
            str(getattr(settings, "BACKTEST_RISK_PER_TRADE_PCT", "0.01"))
        )
        risk_amount = available * risk_pct
        distance = abs(entry - stop)
        if distance <= 0:
            return None
        quantity = int(risk_amount / distance)
        if quantity < 1:
            quantity = 1
        notional_cap = available / entry
        if quantity > notional_cap:
            quantity = int(notional_cap)
        if quantity < 1:
            return None
        return Decimal(quantity)