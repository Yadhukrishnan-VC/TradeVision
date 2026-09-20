import asyncio
import logging
from typing import List

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
                    # Create ExecutionRequest and process through existing engine
                    from apps.execution.infrastructure.models import ExecutionRequest
                    from core.context_processing import generate_correlation_ids
                    from django.db import transaction

                    correlation_id, causation_id = generate_correlation_ids()

                    with transaction.atomic():
                        exec_req = ExecutionRequest.objects.create(
                            idempotency_key=f"live_{int(time.time())}_{exec_count}",
                            account_id=getattr(config, "default_account_id", "account_1"),
                            symbol=signal.instrument_symbol,
                            side="BUY",
                            quantity=config.live_trading_quantity or 10,
                            entry_price=signal.last_price if hasattr(signal, "last_price") else None,
                            stop_loss=config.live_trading_stop_loss,
                            correlation_id=correlation_id,
                            causation_id=causation_id,
                            risk_approved_event_id=f"live_approval_{int(time.time())}",
                            rule_id=rule_id,
                            event_type="live_signal",
                            status="CREATED",
                        )

                    # Process through existing execution engine
                    try:
                        result = execution_engine.process_order(str(exec_req.id))
                        executed_count += 1
                        logger.info(
                            f"Order executed: {exec_req.id} status={result.get('status')}"
                        )
                        order_count += 1
                    except Exception as e:
                        logger.error(
                            f"Order execution failed: {exec_req.id}: {e}",
                            exc_info=True,
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