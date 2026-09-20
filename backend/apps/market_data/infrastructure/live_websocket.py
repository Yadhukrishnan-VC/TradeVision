import asyncio
import json
import time
import logging
from typing import Optional, Callable, Dict, Any, List

from core.config import config

logger = logging.getLogger(__name__)


class LiveKiteWebSocket:
    """Live WebSocket client for Kite Connect market data.

    Connects to wss://ws.kite.trade and subscribes to live tick data
    for watchlist symbols. Publishes events to the Redis event bus.
    """

    def __init__(
        self,
        symbols: List[str],
        exchange: str = "NSE",
        on_tick_callback: Optional[Callable[[Dict], None]] = None,
    ):
        self.symbols = symbols
        self.exchange = exchange
        self.on_tick_callback = on_tick_callback
        self.ws: Optional[Any] = None
        self.running = False
        self.connect_time: Optional[float] = None
        self.last_tick_time: Optional[float] = None
        self.candle_data: Dict[str, Dict] = {
            s: {"open": None, "high": None, "low": None, "close": None, "volume": 0} for s in symbols
        }

    async def connect(self) -> None:
        """Establish WebSocket connection to Kite Connect."""
        import aiohttp

        api_key = config.zerodha_api_key or ""
        if not api_key:
            logger.error("ZERODHA_API_KEY not configured")
            return

        # Kite WebSocket URL
        ws_url = "wss://ws.kite.trade"

        # Build subscription message
        tokens = []
        for symbol in self.symbols:
            # In production, map symbol -> instrument token from Kite
            # For now, use a placeholder format
            tokens.append(f"NSE:{symbol}")

        subscribe_message = {
            "a": "subscribe",
            "v": tokens,
        }

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(ws_url) as ws:
                self.ws = ws
                await ws.send_json(subscribe_message)

                self.running = True
                self.connect_time = time.time()

                logger.info(f"WebSocket connected for symbols: {self.symbols}")

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            await self._handle_message(data)
                        except (json.JSONDecodeError, Exception) as e:
                            logger.error(f"Error handling websocket message: {e}")

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {ws.exception()}")
                        break

                    elif msg.type == aiohttp.WSMsgType.CLOSE:
                        logger.info("WebSocket connection closed")
                        self.running = False
                        break

                # Ensure session closed properly
                await ws.close()

    async def _handle_message(self, data: Dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        # Kite WS message format: {"ohlc": {...}, "ltp": ..., "ohlc_change": ...}
        instrument = data.get("instrument", "")
        ltp = data.get("ltp")
        ohlc = data.get("ohlc", {})

        if ltp is None:
            return

        # Extract symbol from instrument string
        # Format: "NSE:RELIANCE" or similar
        symbol = (
            instrument.split(":")[-1] if ":" in instrument else instrument
        )

        # Update candle data
        if symbol in self.candle_data:
            cd = self.candle_data[symbol]
            if ohlc:
                cd["open"] = ohlc.get("open", cd["open"])
                cd["high"] = ohlc.get("high", cd["high"])
                cd["low"] = ohlc.get("low", cd["low"])
                cd["close"] = ohlc.get("close", ltp)
            cd["volume"] = ohlc.get("volume", 0) if ohlc else 0

        # Prepare tick data package
        tick_data = {
            "symbol": symbol,
            "exchange": self.exchange,
            "last_price": ltp,
            "bid_price": data.get("bid_price"),
            "ask_price": data.get("ask_price"),
            "volume": data.get("volume", 0),
            "timestamp": time.time(),
            "ohlc": {
                "open": self.candle_data[symbol]["open"],
                "high": self.candle_data[symbol]["high"],
                "low": self.candle_data[symbol]["low"],
                "close": ltp,
                "volume": self.candle_data[symbol]["volume"],
            },
            "tick_id": data.get("tick_id"),
            "ohlc_change": data.get("ohlc_change"),
        }

        # Callback if provided
        if self.on_tick_callback:
            try:
                self.on_tick_callback(tick_data)
            except Exception as e:
                logger.error(f"Error in tick callback: {e}")

        # Log live tick
        logger.debug(f"Tick: {symbol} = {ltp}")

    async def start_background(self) -> None:
        """Start WebSocket connection in background task."""
        while self.running:
            try:
                await self.connect()
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                self.running = False
                self.connect_time = None

            # Exponential backoff reconnection
            wait_time = min(2 ** (5 if not self.connect_time else 0), 30)
            logger.info(f"Reconnecting WebSocket in {wait_time}s...")
            await asyncio.sleep(wait_time)

    def stop(self) -> None:
        """Stop the WebSocket connection."""
        self.running = False
        if self.ws:
            try:
                asyncio.create_task(self.ws.close())
            except Exception:
                pass
        logger.info("WebSocket connection stopped")


# Factory function to create websocket with event bus publishing
def create_live_websocket(
    symbols: List[str],
    on_tick_callback: Callable[[Dict], None],
) -> LiveKiteWebSocket:
    """Create a live WebSocket instance with event bus integration."""
    ws = LiveKiteWebSocket(symbols=symbols, on_tick_callback=on_tick_callback)
    return ws