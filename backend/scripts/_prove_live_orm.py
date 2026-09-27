"""Drive the PRODUCTION on_tick_callback closure to the ExecutionRequest
ORM write, mocking only the tick source and the signal generator's
process_tick (which is non-functional today because _rule_matches_conditions
does not exist). Everything inside on_tick_callback (sync_to_async ORM write,
ExecutionEngine.execute_order) runs the real code.

Run: docker exec infra-backend-1 env EXECUTION_ENGINE_ENABLED=True BROKER_ENVIRONMENT=sandbox \
     python manage.py shell < scripts/_prove_live_orm.py
"""
import os
import logging

os.environ.setdefault("EXECUTION_ENGINE_ENABLED", "True")
os.environ.setdefault("BROKER_ENVIRONMENT", "sandbox")

import django

django.setup()

logging.basicConfig(level=logging.INFO)


class FakeSignal:
    """Duck-typed Signal returned by the mocked process_tick."""

    id = "mock-signal-001"
    instrument_symbol = "RELIANCE"
    direction = "BUY"
    confidence_hint = 0.92
    last_price = 2500.0


class FakeTickSource:
    """Replaces create_live_websocket: call the real callback once, then stop."""

    def __init__(self, callback, symbols):
        self.callback = callback
        self.symbols = symbols

    async def start_background(self):
        print("FakeTickSource.start_background: delivering one tick")
        await self.callback(
            {
                "symbol": "RELIANCE",
                "last_price": 2500.0,
                "ohlc": {
                    "open": 2480.0,
                    "high": 2510.0,
                    "low": 2475.0,
                    "volume": 1234,
                },
                "timestamp": 1700000000.0,
            }
        )
        print("FakeTickSource.start_background: tick delivered")


import apps.execution.tasks.live_trading_task as ltt
from apps.signals_engine.application.live_signal_generator import (
    LiveSignalGenerator,
)

# Mock the tick source factory so the real on_tick_callback closure is used.
ltt.create_live_websocket = lambda symbols, on_tick_callback: FakeTickSource(
    on_tick_callback, symbols
)
# Mock process_tick to return a BUY signal above the 0.6 confidence gate.
async def fake_process_tick(self, tick_data):
    return FakeSignal()


LiveSignalGenerator.process_tick = fake_process_tick

os.environ["EXECUTION_ENGINE_ENABLED"] = "True"

# Python 3.12: asyncio.get_event_loop() inside django.setup() returns a closed
# loop; give the task's loop.run_until_complete a fresh current loop.
import asyncio

_fresh = asyncio.new_event_loop()
asyncio.set_event_loop(_fresh)

result = ltt.run_live_trading_session(symbols=["RELIANCE"], rule_id="breakout_v1")
asyncio.set_event_loop(None)
print(f"SESSION RESULT: {result}")

from apps.execution.infrastructure.models import ExecutionRequest

n = ExecutionRequest.objects.filter(idempotency_key__startswith="live_").count()
print(f"ExecutionRequest rows created by live task: {n}")