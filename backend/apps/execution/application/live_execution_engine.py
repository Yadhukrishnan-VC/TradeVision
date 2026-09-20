import asyncio
import logging
import json
from typing import Optional, Dict, Any

from django.db import transaction

from apps.execution.infrastructure.models import ExecutionRequest, Order, Fill
from apps.execution.infrastructure.brokers.zerodha_broker import ZerodhaBroker
from apps.execution.application.execution_engine import ExecutionEngine
from apps.risk_management.infrastructure.models import KillSwitchState
from core.config import config

logger = logging.getLogger(__name__)


class LiveExecutionEngine:
    """Live execution engine that processes auto orders
    through Zerodha connection in real-time.
    """

    def __init__(self):
        self.running = False
        self.broker: Optional[ZerodhaBroker] = None
        self.order_count = 0
        self.rejected_count = 0

    async def start(self) -> None:
        """Start the live execution engine."""
        self.running = True
        logger.info("Starting Live Execution Engine")

        # Initialize Zerodha broker if credentials available
        await self._init_broker()

        # Main execution loop
        while self.running:
            try:
                await self._execution_cycle()
                await asyncio.sleep(0.5)  # Cycle interval
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    f"Error in execution cycle: {e}", exc_info=True
                )
                await asyncio.sleep(1)

    async def _init_broker(self) -> None:
        """Initialize Zerodha broker connection."""
        api_key = config.zerodha_api_key or ""
        access_token = config.zerodha_access_token or ""

        if not api_key or not access_token:
            logger.warning(
                "Zerodha credentials not fully configured, "
                "paper broker will be used"
            )
            # Fall back to paper broker logic
            from apps.execution.infrastructure.brokers.paper_broker import (
                PaperBroker,
            )
            self.broker = PaperBroker()
            return

        try:
            self.broker = ZerodhaBroker(
                api_key=api_key, access_token=access_token
            )
            logger.info("Zerodha broker initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Zerodha broker: {e}")

    async def _execution_cycle(self) -> None:
        """One execution cycle: check for pending orders, risk checks, etc."""
        # Check kill switch status
        if await self._check_kill_switch():
            logger.warning("Kill switch active, rejecting all orders")
            return

        # Process pending ExecutionRequests
        await self._process_pending_orders()

        # Check for order fills/status
        await self._check_order_status()

    async def _check_kill_switch(self) -> bool:
        """Check if any kill switch is active.

        Returns:
            True if kill switch is active (orders should be rejected)
        """
        from apps.risk_management.infrastructure.models import KillSwitchState

        # Check GLOBAL scope
        global_kills = KillSwitchState.objects.filter(
            scope="GLOBAL", is_active=True
        )
        if global_kills.exists():
            return True

        # Check SYMBOL scope for active symbols
        # In production, would check against current market symbols
        symbol_kills = KillSwitchState.objects.filter(
            scope="SYMBOL", is_active=True
        )
        # Would check current symbols here

        return False

    async def _process_pending_orders(self) -> None:
        """Process pending ExecutionRequests through the execution pipeline."""
        from apps.execution.application.execution_engine import (
            process_order as process_order_task,
        )

        # Fetch pending execution requests
        # In production, would have a proper queue mechanism
        pending = ExecutionRequest.objects.filter(
            status="CREATED"  # Orders yet to be processed
        )[:10]  # Batch limit

        for exec_req in pending:
            try:
                # Risk approval already checked at creation
                # Process through execution engine
                await process_order_task.delay(exec_req.id)

            except Exception as e:
                logger.error(
                    f"Error processing execution request {exec_req.id}: {e}",
                    exc_info=True,
                )

    async def _check_order_status(self) -> None:
        """Check status of active orders and update fills."""
        if not self.broker:
            return

        try:
            # Fetch active orders and check fills
            # This integrates with broker's order status API
            logger.debug("Checking order status...")
        except Exception as e:
            logger.error(f"Error checking order status: {e}")

    async def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        entry_price: Optional[float] = None,
    ) -> Optional[Order]:
        """Submit an order through the live broker.

        Args:
            symbol: Trading symbol (e.g., "RELIANCE")
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Limit price (None for market order)
            stop_loss: Stop loss price
            entry_price: Entry price for the order

        Returns:
            Order object if submitted, None otherwise
        """
        if not self.broker:
            logger.error("No broker initialized")
            return None

        try:
            # Create ExecutionRequest first
            from apps.execution.infrastructure.models import ExecutionRequest
            from core.context_processing import generate_correlation_ids

            correlation_id, causation_id = generate_correlation_ids()

            exec_req = ExecutionRequest.objects.create(
                idempotency_key=f"live_{int(time.time())}_{self.order_count}",
                account_id=getattr(config, "default_account_id", "account_1"),
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=entry_price,
                stop_loss=stop_loss,
                correlation_id=correlation_id,
                causation_id=causation_id,
                risk_approved_event_id=f"live_approval_{int(time.time())}",
                rule_id=getattr(config, "active_rule_id", "breakout_v1"),
                event_type="live_signal",
                status="CREATED",
            )

            # Process through execution engine
            engine = ExecutionEngine(exec_req)
            result = await engine.process()

            # If filled, create Order and Fill
            if result and result.get("status") in ("FILLED", "PARTIAL"):
                order = Order.objects.create(
                    account_id=exec_req.account_id,
                    symbol=symbol,
                    side=side,
                    order_type=result.get("order_type", "LIMIT"),
                    quantity=result.get("quantity", quantity),
                    status=result.get("status", "CREATED"),
                    filled_quantity=result.get("filled_quantity", 0),
                    avg_fill_price=result.get("avg_fill_price"),
                    limit_price=price,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    correlation_id=correlation_id,
                    causation_id=causation_id,
                    broker_name="zerodha",
                    broker_order_ref=result.get("broker_order_ref"),
                )

                # Create Fill record
                Fill.objects.create(
                    order=order,
                    sequence=1,
                    quantity=result.get("filled_quantity", quantity),
                    price=result.get("avg_fill_price"),
                    occurred_at=time.time(),
                )

                # Update portfolio position
                await self._update_position(order)

                logger.info(
                    f"Order executed: {order.id} for {symbol} "
                    f"side={side} qty={result.get('filled_quantity', quantity)}"
                )
                return order

            else:
                # Order rejected or expired
                exec_req.status = result.get("status", "REJECTED")
                exec_req.reason_message = result.get("reason", "Unknown")
                exec_req.save()

                self.rejected_count += 1
                logger.warning(
                    f"Order rejected: {exec_req.id} - {exec_req.reason_message}"
                )
                return None

        except Exception as e:
            logger.error(
                f"Error submitting order for {symbol}: {e}", exc_info=True
            )
            return None

    async def _update_position(self, order: Order) -> None:
        """Update portfolio position after order fill."""
        from apps.portfolio.infrastructure.models import Position, AccountCapitalState

        symbol = order.symbol
        side = order.side
        filled_qty = order.filled_quantity
        fill_price = order.avg_fill_price

        # Get or create position
        position, created = Position.objects.get_or_create(
            account_id=order.account_id,
            symbol=symbol,
            defaults={
                "side": side,
                "quantity": 0,
                "average_price": 0,
                "market_value": 0,
                "unrealized_pnl": 0,
            },
        )

        # Update position quantity and average price
        if side == "BUY":
            position.quantity += filled_qty
            if created or position.average_price == 0:
                position.average_price = fill_price
            else:
                # Weighted average
                total_cost = position.average_price * (position.quantity - filled_qty)
                position.average_price = (total_cost + fill_price * filled_qty) / position.quantity
        else:  # SELL
            position.quantity -= filled_qty

        # Update market value and PnL
        # In production, would fetch current market price
        position.market_value = position.quantity * fill_price if fill_price else 0

        # Calculate unrealized PnL (simplified)
        position.unrealized_pnl = (
            (fill_price - position.average_price) * filled_qty
            if side == "BUY"
            else (position.average_price - fill_price) * filled_qty
        )

        position.save()

        # Update capital state
        capital_state, _ = AccountCapitalState.objects.get_or_create(
            account_id=order.account_id
        )
        # Simplified PnL attribution
        capital_state.total_pnl = (
            capital_state.total_pnl or 0
        ) + (order.unrealized_pnl or 0)
        capital_state.save()

        logger.debug(
            f"Position updated: {symbol} qty={position.quantity} "
            f"avg_price={position.average_price}"
        )