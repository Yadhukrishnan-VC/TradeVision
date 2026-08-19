from __future__ import annotations

import logging
from decimal import Decimal
from typing import Protocol

from apps.execution.application.ports import BrokerAdapter
from apps.execution.domain.exceptions import BrokerRejection, ExecutionDomainError
from apps.execution.domain.value_objects import (
    BrokerAck,
    BrokerCancelResult,
    BrokerOrderStatus,
    OrderPlacementRequest,
)
from apps.portfolio.domain.value_objects import Side

logger = logging.getLogger(__name__)

_SANDBOX_ROOT = "https://sandbox.kite.trade"
_PRODUCTION_ROOT = "https://api.kite.trade"
# Shared Kite sandbox demo app — safe to keep in plain text: not tied to a
# real account or real money (kite.trade/docs/connect/v3/sandbox/).
_SANDBOX_API_KEY = "sandboxdemo"
_SANDBOX_API_SECRET = "sandboxdemo-secret"
# Sandbox serves SDK routes under an /oms prefix except the instruments dumps.
_SANDBOX_PASSTHROUGH_ROUTES = frozenset({"market.instruments.all", "market.instruments"})
_DEFAULT_EXCHANGE = "NSE"

# Kite order statuses (kiteconnect.enums.Status) -> internal BrokerOrderStatus
# status vocabulary used by the execution engine.
_KITE_TO_INTERNAL_STATUS = {
    "COMPLETE": "FILLED",
    "OPEN": "OPEN",
    "PENDING": "OPEN",
    "TRIGGER PENDING": "OPEN",
    "CANCELLED": "CANCELLED",
    "REJECTED": "REJECTED",
    "EXPIRED": "EXPIRED",
}

# Kite exceptions that represent an order/input/data rejection. They surface
# through the existing BrokerRejection path — no new error shape. Network /
# token / permission errors propagate instead so the caller can retry.
_KITE_REJECTION_EXCEPTIONS = frozenset({"InputException", "OrderException", "DataException"})

# Kite only accepts LIMIT orders via the API (the sandbox rejects MARKET).
_KITE_ORDER_TYPE = "LIMIT"
_KITE_VARIETY = "regular"


class KiteClient(Protocol):
    """Structural view of the ``kiteconnect.KiteConnect`` surface this adapter
    uses. The real SDK satisfies it; tests inject an in-memory double."""

    def set_access_token(self, token: str) -> None: ...

    def generate_session(self, request_token: str, api_secret: str | None = None) -> dict: ...

    def orders(self) -> list[dict]: ...

    def place_order(self, **kwargs: object) -> str: ...

    def order_history(self, order_id: str) -> list[dict]: ...

    def cancel_order(self, **kwargs: object) -> None: ...


class ZerodhaBroker(BrokerAdapter):
    """Kite Connect live-broker adapter — LIVE-BROKER-EXECUTION-1 (Phase 1).

    - **Sandbox only.** ``BROKER_ENVIRONMENT`` defaults to ``sandbox`` and a
      ``live`` value fails Django startup via ``apps.execution.checks`` until
      the Phase 2 explicit unlock exists (ADR-030). In sandbox mode the
      adapter falls back to the shared Kite demo app (``sandboxdemo`` /
      ``sandbox.kite.trade``) — no real money is ever at risk.
    - **Exactly the ``BrokerAdapter`` protocol.** This adapter implements
      ``place_order`` / ``cancel_order`` / ``get_order_status`` and nothing
      more; it intentionally mirrors the paper broker's behaviour rather than
      adding capability (no auto-sizing, no order splitting).
    - **Idempotent placement.** The internal ``correlation_id`` is sent as the
      Kite order ``tag``. Before placing, recent orders are scanned for a
      matching tag; a retry after a mid-request timeout reuses the existing
      broker order instead of placing a second one. If the duplicate check
      itself fails (network), the placement is NOT attempted — the error
      propagates so the retry can re-check.
    - **LIMIT-only mapping.** Kite's API (and the sandbox) only accepts LIMIT
      orders; the internal ``order_type`` is mapped to ``LIMIT`` at the
      configured ``order.price`` (documented in ADR-030).
    """

    def __init__(
        self,
        *,
        client: KiteClient | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        request_token: str | None = None,
        access_token: str | None = None,
        environment: str | None = None,
        api_root: str | None = None,
        product: str | None = None,
    ) -> None:
        from core.config import config

        self._environment = (environment or config.broker_environment).lower()
        self._validate_environment()

        self._api_key = api_key or config.zerodha_api_key
        self._api_secret = api_secret or config.zerodha_api_secret
        self._request_token = request_token or config.zerodha_request_token
        self._access_token = access_token or config.zerodha_access_token
        self._product = (product or config.zerodha_product or "MIS").upper()
        self._api_root = api_root or (
            _SANDBOX_ROOT if self._environment == "sandbox" else _PRODUCTION_ROOT
        )

        if self._environment == "sandbox":
            if not self._api_key:
                self._api_key = _SANDBOX_API_KEY
            if not self._api_secret:
                self._api_secret = _SANDBOX_API_SECRET

        # Injected client for tests; None means "build lazily from settings".
        self._client = client

    # ------------------------------------------------------------------
    # BrokerAdapter protocol
    # ------------------------------------------------------------------

    def place_order(self, order: OrderPlacementRequest) -> BrokerAck:
        client = self._get_client()
        tag = str(order.correlation_id)

        # Idempotency: only place after confirming no prior broker-side order
        # carries this correlation tag. A failed duplicate check propagates so
        # a retry re-checks instead of risking a second order.
        existing = self._existing_order_with_tag(client, tag)
        if existing is not None:
            return BrokerAck(
                broker_order_ref=existing,
                message="reused existing order (idempotent retry)",
            )

        exchange, tradingsymbol = self._split_symbol(order.symbol)
        try:
            ref = client.place_order(
                variety=_KITE_VARIETY,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type="BUY" if order.side is Side.LONG else "SELL",
                quantity=int(order.quantity),
                product=self._product,
                order_type=_KITE_ORDER_TYPE,
                price=float(order.price),
                tag=tag,
            )
        except Exception as exc:
            rejection = self._as_rejection(exc)
            if rejection is not None:
                raise rejection from exc
            raise
        return BrokerAck(broker_order_ref=str(ref))

    def cancel_order(self, broker_order_ref: str) -> BrokerCancelResult:
        client = self._get_client()
        try:
            client.cancel_order(variety=_KITE_VARIETY, order_id=broker_order_ref)
        except Exception as exc:
            rejection = self._as_rejection(exc)
            if rejection is not None:
                return BrokerCancelResult(
                    broker_order_ref=broker_order_ref,
                    cancelled=False,
                    message=rejection.reason_message,
                )
            raise
        return BrokerCancelResult(
            broker_order_ref=broker_order_ref,
            cancelled=True,
            message="cancelled",
        )

    def get_order_status(self, broker_order_ref: str) -> BrokerOrderStatus:
        client = self._get_client()
        try:
            history = client.order_history(order_id=broker_order_ref)
        except Exception as exc:
            rejection = self._as_rejection(exc)
            if rejection is not None:
                return BrokerOrderStatus(
                    broker_order_ref=broker_order_ref,
                    status="UNKNOWN",
                )
            raise
        if not history:
            return BrokerOrderStatus(broker_order_ref=broker_order_ref, status="UNKNOWN")

        latest = history[-1]
        status = self._normalise_status(str(latest.get("status", "OPEN")))
        filled = latest.get("filled_quantity") or 0
        if status == "OPEN" and filled:
            status = "PARTIALLY_FILLED"
        avg_price = latest.get("average_price") or latest.get("avg_price")
        return BrokerOrderStatus(
            broker_order_ref=broker_order_ref,
            status=status,
            filled_quantity=Decimal(str(filled)),
            avg_fill_price=Decimal(str(avg_price)) if avg_price is not None else None,
        )

    # ------------------------------------------------------------------
    # Session + client construction
    # ------------------------------------------------------------------

    def _validate_environment(self) -> None:
        if self._environment not in ("sandbox", "live"):
            raise ExecutionDomainError(
                f"BROKER_ENVIRONMENT must be 'sandbox' or 'live'; got "
                f"{self._environment!r}.",
                code="INVALID_BROKER_ENVIRONMENT",
            )
        if self._environment == "live":
            # Defense-in-depth: the Django startup check already blocks `live`
            # (execution.E001); the adapter refuses it too because the Phase 2
            # explicit unlock (ADR-030) does not exist in this batch.
            raise ExecutionDomainError(
                "ZerodhaBroker refuses BROKER_ENVIRONMENT=live: the Phase 2 "
                "explicit live unlock (ADR-030) is not implemented, so live "
                "execution is unreachable in this batch.",
                code="LIVE_UNREACHABLE_PHASE_1",
            )

    def _get_client(self) -> KiteClient:
        if self._client is None:
            self._client = self._build_client()
        self._bootstrap_session()
        return self._client

    def _build_client(self) -> KiteClient:
        try:
            from kiteconnect import KiteConnect
        except ImportError as exc:
            raise ExecutionDomainError(
                "kiteconnect package not installed. Install with: "
                "pip install kiteconnect",
                code="KITECONNECT_NOT_INSTALLED",
            ) from exc
        client = KiteConnect(api_key=self._api_key, root=self._api_root)  # type: ignore[no-any-return]
        if self._environment == "sandbox":
            self._patch_sandbox_routes(client)
        return client

    def _bootstrap_session(self) -> None:
        if self._access_token:
            self._client.set_access_token(self._access_token)
            return
        if self._request_token:
            session = self._client.generate_session(
                self._request_token, api_secret=self._api_secret
            )
            self._client.set_access_token(session["access_token"])
            # Persist so later calls skip the single-use token exchange.
            self._access_token = session["access_token"]
            return
        raise ExecutionDomainError(
            "No Zerodha access token configured. Set ZERODHA_ACCESS_TOKEN "
            "(or a single-use ZERODHA_REQUEST_TOKEN to exchange out-of-band).",
            code="NO_ZERODHA_ACCESS_TOKEN",
        )

    # ------------------------------------------------------------------
    # Helpers (kept static/isolated so unit tests do not need kiteconnect)
    # ------------------------------------------------------------------

    @staticmethod
    def _patch_sandbox_routes(client: object) -> None:
        """Prefix every SDK route with ``/oms`` except the instruments dumps."""
        routes = getattr(client, "_routes", {})
        if not routes:
            return
        client._routes = {
            key: value if key in _SANDBOX_PASSTHROUGH_ROUTES else "/oms" + value
            for key, value in routes.items()
        }

    @staticmethod
    def _split_symbol(symbol: str) -> tuple[str, str]:
        """Split an internal symbol into Kite (exchange, tradingsymbol).

        Internal symbols may carry an exchange prefix (``NSE:RELIANCE``);
        unprefixed symbols are assumed to trade on NSE (the paper broker's
        default market — documented in ADR-030).
        """
        if ":" in symbol:
            exchange, tradingsymbol = symbol.split(":", 1)
            return exchange.upper(), tradingsymbol
        return _DEFAULT_EXCHANGE, symbol

    @staticmethod
    def _existing_order_with_tag(client: KiteClient, tag: str) -> str | None:
        """Return the broker order id for a prior order carrying ``tag``.

        Raises on any transport failure: the caller must NOT place when it
        cannot confirm no duplicate exists.
        """
        orders = client.orders() or []
        for order in orders:
            if order.get("tag") == tag and order.get("order_id"):
                return str(order["order_id"])
        return None

    @classmethod
    def _as_rejection(cls, exc: Exception) -> BrokerRejection | None:
        """Map a Kite rejection-class exception to BrokerRejection, else None."""
        if type(exc).__name__ in _KITE_REJECTION_EXCEPTIONS:
            return BrokerRejection(
                reason_code="BROKER_REJECTED",
                reason_message=str(exc) or type(exc).__name__,
            )
        return None

    @staticmethod
    def _normalise_status(kite_status: str) -> str:
        status = _KITE_TO_INTERNAL_STATUS.get(kite_status.upper())
        if status is None:
            logger.warning(
                "zerodha_broker_unknown_status",
                extra={"kite_status": kite_status},
            )
            return "OPEN"
        return status
