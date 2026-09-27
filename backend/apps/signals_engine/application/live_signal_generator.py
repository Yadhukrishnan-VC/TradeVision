import asyncio
import time
import logging
import uuid
from asgiref.sync import sync_to_async
from typing import Optional, Dict, Any, List

from django.db import transaction

from apps.signals_engine.infrastructure.models import Signal
from apps.rule_engine.infrastructure.models import RuleConfig
from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

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

    async def _get_active_rule_ids(self) -> List[str]:
        """Get IDs of active (enabled, not soft-deleted) rules."""
        from apps.rule_engine.infrastructure.models import RuleConfig

        rule_ids = await sync_to_async(
            lambda: list(
                RuleConfig.objects.filter(enabled=True, is_deleted=False)
            ).values_list("rule_id", flat=True)
        )()
        return rule_ids

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

        active_rules = await sync_to_async(
            lambda: list(
                RuleConfig.objects.filter(enabled=True, is_deleted=False)
            )
        )()

        for rule in active_rules:
            try:
                # Evaluate rule against current market data
                # step 2: feed live tick into candle-aggregation → TA → IntelligencePacket pipeline
                # then call real rule classes from apps/rule_engine/domain/rules/*.py
                # VOLATILITYBREAKOUT_RULE cleared GO status in evidence runs
                from apps.rule_engine.domain.rules.volatility_breakout import (
                    VolatilityBreakoutRule,
                )
                breakout_rule = VolatilityBreakoutRule(
                    rule_id=rule.rule_id,
                    symbol=symbol,
                    ltp=ltp,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    volume=volume,
                )
                should_fire = breakout_rule.evaluate()

                if should_fire:
                    # Direction determined by real rule class (VolatilityBreakoutRule etc.)
                    # do not hand-construct direction in live task
                    direction = "WAIT"  # placeholder; real rule class will set direction
                    confidence_hint = 0.5  # placeholder; real rule class will set confidence

                    # Create signal via sync_to_async to avoid
                    # Django ORM in async context.
                    signal = await sync_to_async(
                        lambda: Signal.objects.create(
                            account_id=self._get_account_id(),
                            instrument_symbol=symbol,
                            timeframe="1min",
                            direction=direction,
                            confidence_hint=confidence_hint,
                            indicator_snapshot=self._build_indicator_snapshot(
                                rule, tick_data
                            ),
                            source_alert_id=f"live_{rule.rule_id}_{int(time.time())}",
                        )
                    )()

                    # Publish signal event to event bus
                    get_event_bus().publish(
                        DomainEvent.create(
                            event_type="signals_engine.signal_generated",
                            payload={
                                "signal_id": str(signal.id),
                                "symbol": symbol,
                                "direction": direction,
                                "confidence": signal.confidence_hint,
                                "rule_id": rule.rule_id,
                                "price": ltp,
                                "timestamp": time.time(),
                                "source": "live_signal_generator",
                            },
                            correlation_id=uuid.uuid4(),
                        )
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

    # _determine_direction removed — direction determined by real rule class
    # (VolatilityBreakoutRule etc.) — do not hand-construct direction in live task

    # _calculate_confidence removed — confidence determined by real rule class
    # (VolatilityBreakoutRule etc.) — do not hand-construct confidence in live task
    # Placeholder only; real rule class will set confidence

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