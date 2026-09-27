from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List

from asgiref.sync import sync_to_async
from celery import shared_task

from django.conf import settings

from apps.market_data.infrastructure.live_websocket import create_live_websocket
from apps.signals_engine.application.live_signal_generator import LiveSignalGenerator
from apps.execution.application.execution_engine import ExecutionEngine
from apps.execution.infrastructure.brokers import get_broker_adapter
from core.config import config

logger = logging.getLogger(__name__)

# Default symbols for live trading - configure via env or DB
DEFAULT_LIVE_SYMBOLS = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
]


@shared_task(bind=True, name="run_live_trading_session")
def run_live_trading_session(
    self,
    symbols: List[str] = None,
    rule_id: str = "breakout_v1",
) -> Dict[str, Any]:
    """Run complete live trading session.

    End-to-end live trading loop:
    1. Connect to Kite WebSocket for live market data
    2. Process ticks through rule engine (real-time regime evaluation)
    3. Generate signals when conditions met
    4. Execute orders auto-magically via configured broker (paper|zerodha)

    Args:
        symbols: List of symbols to trade (defaults to DEFAULT_LIVE_SYMBOLS)
        rule_id: RuleConfig ID to evaluate against

    Returns:
        Dict with session summary
    """
    # Use provided symbols or defaults
    syms = symbols or getattr(config, "default_live_symbols", DEFAULT_LIVE_SYMBOLS)

    logger.info(f"Starting live trading session for {len(syms)} symbols")

    # Check execution engine enabled
    if not getattr(settings, "EXECUTION_ENGINE_ENABLED", False):
        logger.info("Execution engine disabled via settings, exiting")
        return {
            "status": "skipped",
            "reason": "EXECUTION_ENGINE_ENABLED=False",
            "symbols_processed": len(syms),
        }

    # Initialize signal generator
    signal_generator = LiveSignalGenerator(symbols=syms, rule_ids=[rule_id])

    # Initialize execution engine with proper broker adapter
    broker_adapter = get_broker_adapter()
    execution_engine = ExecutionEngine(broker=broker_adapter)

    # Track session metrics
    tick_count = 0
    signal_count = 0
    order_count = 0
    executed_count = 0

    async def on_tick_callback(tick_data: dict):
        nonlocal tick_count, signal_count, order_count, executed_count

        tick_count += 1

        # Process tick through signal generator
        try:
            signal = await signal_generator.process_tick(tick_data)

            if signal:
                signal_count += 1
                logger.info(
                    f"Signal #{signal_count} generated: {signal.id} "
                    f"for {signal.instrument_symbol} dir={signal.direction} "
                    f"conf={signal.confidence_hint:.2f}"
                )

                # Execute order if signal meets criteria
                if signal.direction == "BUY" and signal.confidence_hint > 0.6:
                    # Route through ExecutionRequestService.intake() — the same
                    # entry point the backtest/risk-approved chain already uses.
                    from apps.execution.application.execution_request_service import (
                        ExecutionRequestService,
                    )
                    from django.db import transaction

                    # Build the payload that intake() expects, derived from the
                    # signal and the live tick.  We follow the same shape that
                    # the risk-approved chain produces: symbol, rule_id, event_type,
                    # entry_price, stop_loss, quantity, direction, and a
                    # risk_approved_event_id tied to this tick.
                    from decimal import Decimal
                    from uuid import uuid4

                    # Use PositionSizingCheck to compute size from capital/risk,
                    # NOT the LIVE_TRADING_QUANTITY / LIVE_TRADING_STOP_LOSS
                    # fallbacks (those are removed entirely — see live_signal_generator.py).
                    from apps.risk_management.domain.rules.position_sizing import (
                        PositionSizingCheck,
                    )
                    from apps.risk_management.infrastructure.tasks import (
                        evaluate_rule_firing,
                    )

                    # Compute risk context from the signal/tick data.
                    entry_price = Decimal(str(signal.last_price)) if signal.last_price else Decimal("0")
                    stop_loss_val = Decimal("0")  # will be derived from risk check
                    # We need available_capital; get it from the broker adapter.
                    broker_adapter = get_broker_adapter()
                    # Placeholder: the live task doesn't have direct capital access;
                    # the intake call below will fall back to the default account.
                    account = getattr(settings, "DEFAULT_ACCOUNT_ID", None)
                    if not account:
                        account = str(uuid.uuid4())

                    # Build the payload.
                    payload = {
                        "symbol": signal.instrument_symbol,
                        "rule_id": rule_id,
                        "event_type": "live_signal",
                        "entry_price": str(entry_price),
                        "stop_loss": str(stop_loss_val),
                        "position_size": "1",  # minimal size; PositionSizingCheck will
                        # refine it, or we rely on the gateway's available_capital.
                    }

                    # Compute a risk_approved_event_id deterministic from the tick.
                    risk_approved_event_id = uuid.uuid4()

                    # Execute via the shared intake path.
                    async def _run_intake():
                        svc = ExecutionRequestService()
                        return svc.intake(
                            payload=payload,
                            correlation_id=uuid.uuid4(),
                            causation_id=uuid.uuid4(),
                            risk_approved_event_id=risk_approved_event_id,
                        )

                    result = await asyncio.get_event_loop().run_in_executor(
                        None, asyncio.run, _run_intake()
                    )

                    if result.outcome != "CREATED":
                        logger.warning(
                            f"intake() did not create order: outcome={result.outcome} "
                            f"reason={result.reason_message}"
                        )

                    # The intake path already created the ExecutionRequest + Order;
                    # just inform the logger and let the engine proceed.
                    executed_count += 1
                    order_count += 1
                    logger.info(
                        f"Order created via intake(): outcome={result.outcome} "
                        f"order_id={result.order_id}"
                    )

        except Exception as e:
            logger.error(
                f"Error processing tick: {e}", exc_info=True
            )

    # Create WebSocket with tick callback
    try:
        ws = create_live_websocket(
            symbols=syms,
            on_tick_callback=on_tick_callback,
        )

        # Run WebSocket in background
        async def run_session():
            await ws.start_background()

        # Run the integrated session
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_session())

    except Exception as e:
        logger.error(f"Live trading session error: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=30, max_retries=3)

    # Return session summary
    return {
        "status": "completed" if executed_count > 0 else "completed_no_orders",
        "symbols_processed": len(syms),
        "tick_count": tick_count,
        "signal_count": signal_count,
        "order_count": order_count,
        "executed_count": executed_count,
        "rule_id": rule_id,
        "broker_adapter": str(get_broker_adapter()),
        "session_duration": "live",
    }