import asyncio
import time
import logging
from typing import Optional, Dict, Any, List

from django.db import transaction

from apps.signals_engine.infrastructure.models import Signal
from apps.rule_engine.infrastructure.models import RuleConfig
from apps.eventbus.application.services import event_bus

logger = logging.getLogger(__name__)


class LiveSignalGenerator:
    """Real-time signal generator that processes live market data
    and generates trading signals based on rule engine evaluation.
    """

    def __init__(
        self,
        symbols: List[str],
        rule_ids: Optional[List[str]] = None,
    ):
        self.symbols = symbols
        self.rule_ids = rule_ids or self._get_active_rule_ids()
        self.running = False
        self.last_signal_time: Dict[str, float] = {s: 0 for s in symbols}
        self.min_signal_interval = 0.5  # minimum seconds between signals per symbol

    def _get_active_rule_ids(self) -> List[str]:
        """Get IDs of active (enabled, not soft-deleted) rules."""
        from apps.rule_engine.infrastructure.models import RuleConfig

        rules = RuleConfig.objects.filter(
            enabled=True, is_deleted=False
        )
        return list(rules.values_list("rule_id", flat=True))

    async def process_tick(self, tick_data: Dict[str, Any]) -> Optional[Signal]:
        """Process a single tick and generate if conditions met.

        Args:
            tick_data: Tick data dict from market data WebSocket

        Returns:
            Signal object if generated, None otherwise
        """
        symbol = tick_data.get("symbol")
        ltp = tick_data.get("last_price")

        if not symbol or ltp is None:
            return None

        current_time = time.time()
        last_time = self.last_signal_time.get(symbol, 0)

        # Rate limiting per symbol
        if current_time - last_time < self.min_signal_interval:
            return None

        try:
            # Evaluate rule engine for this symbol
            signal = await self._evaluate_rules(tick_data)
            if signal:
                self.last_signal_time[symbol] = current_time
                return signal
        except Exception as e:
            logger.error(f"Error evaluating rules for {symbol}: {e}", exc_info=True)

        return None

    async def _evaluate_rules(self, tick_data: Dict[str, Any]) -> Optional[Signal]:
        """Evaluate all active rules against current tick data.

        Returns Signal if any rule fires, None otherwise.
        """
        from apps.signals_engine.infrastructure.models import Signal

        symbol = tick_data.get("symbol")
        ltp = tick_data.get("last_price")
        ohlc = tick_data.get("ohlc", {})

        if not symbol or ltp is None:
            return None

        # Get current candle data
        open_price = ohlc.get("open")
        high_price = ohlc.get("high")
        low_price = ohlc.get("low")
        volume = ohlc.get("volume", 0)

        # Build market regime data
        from apps.rule_engine.infrastructure.models import RuleConfig
        import json

        active_rules = RuleConfig.objects.filter(
            enabled=True, is_deleted=False
        )

        for rule in active_rules:
            try:
                # Evaluate rule against current market data
                should_fire = await self._rule_matches_conditions(
                    rule, symbol, ltp, open_price, high_price, low_price, volume
                )

                if should_fire:
                    # Determine signal direction based on rule parameters
                    direction = self._determine_direction(rule, tick_data)

                    # Create signal
                    signal = Signal.objects.create(
                        account_id=self._get_account_id(),
                        instrument_symbol=symbol,
                        timeframe="1min",
                        direction=direction,
                        confidence_hint=self._calculate_confidence(rule, tick_data),
                        indicator_snapshot=self._build_indicator_snapshot(
                            rule, tick_data
                        ),
                        source_alert_id=f"live_{rule.rule_id}_{int(time.time())}",
                    )

                    # Publish signal event to event bus
                    await event_bus.publish(
                        topic="signals_engine.signals",
                        message={
                            "signal_id": str(signal.id),
                            "symbol": symbol,
                            "direction": direction,
                            "confidence": signal.confidence_hint,
                            "rule_id": rule.rule_id,
                            "price": ltp,
                            "timestamp": time.time(),
                            "source": "live_signal_generator",
                        },
                    )

                    logger.info(
                        f"Signal generated: {signal.id} for {symbol} "
                        f"direction={direction} rule={rule.rule_id}"
                    )
                    return signal

            except Exception as e:
                logger.error(
                    f"Error evaluating rule {rule.rule_id} for {symbol}: {e}",
                    exc_info=True,
                )
                continue

        return None

    def _determine_direction(
        self, rule: RuleConfig, tick_data: Dict[str, Any]
    ) -> str:
        """Determine signal direction (BUY/SELL/WAIT) based on rule."""
        parameters = rule.parameters or {}

        # Check rule event_type for direction
        event_type = parameters.get("event_type", "breakout")

        if event_type in ("breakout", "price_movement", "gap_movement"):
            # For breakout-type rules, determine based on price position
            # Simplified: BUY on breakout above resistance
            return "BUY"
        elif event_type in ("breakdown", "volume_spike"):
            return "SELL"
        else:
            # Default: WAIT unless conditions clearly met
            return "WAIT"

    def _calculate_confidence(
        self, rule: RuleConfig, tick_data: Dict[str, Any]
    ) -> float:
        """Calculate confidence hint (0-1) based on rule metrics."""
        parameters = rule.parameters or {}

        # Use stored regime metrics from validated_regimes
        regimes = rule.validated_regimes or {}

        # Get the relevant regime status
        regime_status = regimes.get("RANGING", {}).get("status", "NO_GO")

        if regime_status == "GO":
            # Use profit_factor and sharpe from stored data
            pf = regimes.get("RANGING", {}).get("profit_factor", 1.0)
            sr = regimes.get("RANGING", {}).get("sharpe_ratio", 1.0)

            # Convert to 0-1 confidence range
            confidence = min(1.0, (pf + sr) / 4.0)
            return round(confidence, 2)
        elif regime_status == "NO_GO":
            return 0.1
        else:
            return 0.5

    def _build_indicator_snapshot(
        self, rule: RuleConfig, tick_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build indicator snapshot for the signal."""
        ohlc = tick_data.get("ohlc", {})
        return {
            "open": ohlc.get("open"),
            "high": ohlc.get("high"),
            "low": ohlc.get("low"),
            "close": tick_data.get("last_price"),
            "volume": ohlc.get("volume", 0),
            "rsi": ohlc.get("rsi"),
            "atr": ohlc.get("atr"),
            "timestamp": tick_data.get("timestamp"),
        }

    def _get_account_id(self) -> str:
        """Get the current account ID from config."""
        from core.config import config

        # Try to get from account config or use default
        return getattr(config, "default_account_id", "account_1")

    async def start_processing(self) -> None:
        """Start the signal processing loop.

        This should be called as a Celery task or async background task.
        """
        self.running = True
        logger.info(
            f"Starting live signal processing for {len(self.symbols)} symbols"
        )

        while self.running:
            try:
                # Wait for tick events - in production this would
                # be triggered by the WebSocket callback
                await asyncio.sleep(0.1)  # Poll interval

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in signal processing loop: {e}", exc_info=True)

    def stop(self) -> None:
        """Stop the signal generator."""
        self.running = False
        logger.info("Live signal generator stopped")