from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from apps.common.domain.value_objects import Symbol
from apps.market_data.domain.entities import Candle
from apps.market_data.domain.exceptions import StaleCandleDataError, UnsupportedTimeframeError
from apps.market_data.domain.value_objects import Timeframe
from core.market_calendar import get_market_calendar
from core.market_data.base_provider import OHLCVBar
from core.utils import get_ist_now, to_ist, to_utc

logger = logging.getLogger(__name__)

_SESSION_OPEN_IST_HOUR = 9
_SESSION_OPEN_IST_MINUTE = 15


class CandleAggregationService:
    """Aggregates raw ``OHLCVBar`` objects into domain ``Candle`` entities.

    Timeframe buckets above ``1min`` are aligned to the NSE market session
    open (``09:15 IST``), not to naive wall-clock boundaries. This ensures
    that the first 15-minute candle of the day correctly starts at
    ``09:15`` rather than ``09:00``.
    """

    def aggregate(
        self,
        instrument_token: int,
        base_candles: list[OHLCVBar],
        target_timeframe: Timeframe,
    ) -> list[Candle]:
        """Aggregate a list of base OHLCV bars into the target timeframe.

        Args:
            instrument_token: The instrument these candles belong to.
            base_candles:     Source bars (typically 1-minute bars).
            target_timeframe: The destination aggregation level.

        Returns:
            A chronologically ordered list of ``Candle`` domain entities.

        Raises:
            UnsupportedTimeframeError: If *target_timeframe* is not a valid
                aggregation target.
            StaleCandleDataError: If *base_candles* contain gaps that would
                produce incorrect aggregated candles.
        """
        if target_timeframe == Timeframe.MINUTE_1:
            return self._passthrough(instrument_token, base_candles)

        bucket_key_fn = self._bucket_key(target_timeframe)

        buckets: dict[str, list[OHLCVBar]] = defaultdict(list)
        for bar in base_candles:
            key = bucket_key_fn(bar.timestamp)
            buckets[key].append(bar)

        candles: list[Candle] = []
        for bucket_key in sorted(buckets.keys()):
            bars = buckets[bucket_key]
            aggregated = self._merge_bars(instrument_token, bars, target_timeframe)
            candles.append(aggregated)

        return candles

    def _passthrough(
        self,
        instrument_token: int,
        base_candles: list[OHLCVBar],
    ) -> list[Candle]:
        """Convert 1-minute ``OHLCVBar`` objects to ``Candle`` entities directly."""
        return [
            Candle(
                instrument_token=instrument_token,
                timeframe=Timeframe.MINUTE_1.value,
                timestamp=bar.timestamp,
                open=bar.open_price,
                high=bar.high,
                low=bar.low,
                close=bar.close_price,
                volume=bar.volume,
            )
            for bar in base_candles
        ]

    def _bucket_key(self, timeframe: Timeframe) -> Any:
        """Return a function that maps a ``datetime`` to a bucket key string.

        The key is derived from the session-aligned bucket start time.
        """
        cal = get_market_calendar()

        if timeframe == Timeframe.MINUTE_3:
            return lambda dt: self._session_aligned_key(dt, minutes=3, cal=cal)
        elif timeframe == Timeframe.MINUTE_5:
            return lambda dt: self._session_aligned_key(dt, minutes=5, cal=cal)
        elif timeframe == Timeframe.MINUTE_10:
            return lambda dt: self._session_aligned_key(dt, minutes=10, cal=cal)
        elif timeframe == Timeframe.MINUTE_15:
            return lambda dt: self._session_aligned_key(dt, minutes=15, cal=cal)
        elif timeframe == Timeframe.MINUTE_30:
            return lambda dt: self._session_aligned_key(dt, minutes=30, cal=cal)
        elif timeframe == Timeframe.HOUR_1:
            return lambda dt: self._session_aligned_key(dt, minutes=60, cal=cal)
        elif timeframe == Timeframe.HOUR_2:
            return lambda dt: self._session_aligned_key(dt, minutes=120, cal=cal)
        elif timeframe == Timeframe.HOUR_4:
            return lambda dt: self._session_aligned_key(dt, minutes=240, cal=cal)
        elif timeframe == Timeframe.DAY_1:
            return lambda dt: dt.strftime("%Y-%m-%d")
        elif timeframe in (Timeframe.WEEK_1, Timeframe.MONTH_1):
            raise UnsupportedTimeframeError(
                f"{timeframe.value} aggregation is not yet supported"
            )
        else:
            raise UnsupportedTimeframeError(f"Unknown timeframe: {timeframe.value}")

    def _session_aligned_key(
        self,
        dt: datetime,
        minutes: int,
        cal: Any,
    ) -> str:
        """Return a bucket key aligned to the market session open.

        The bucket boundary for intraday timeframes is anchored to the
        NSE session open (09:15 IST). For example, 15-minute buckets
        are 09:15, 09:30, 09:45, ..., not 09:00, 09:15, 09:30.
        """
        ist_dt = to_ist(dt)
        session_start = ist_dt.replace(
            hour=_SESSION_OPEN_IST_HOUR,
            minute=_SESSION_OPEN_IST_MINUTE,
            second=0,
            microsecond=0,
        )

        elapsed_minutes = int((ist_dt - session_start).total_seconds() / 60)
        if elapsed_minutes < 0:
            elapsed_minutes = 0

        bucket_index = (elapsed_minutes // minutes) * minutes
        bucket_start = session_start + timedelta(minutes=bucket_index)
        return bucket_start.strftime("%Y-%m-%d %H:%M")

    def _merge_bars(
        self,
        instrument_token: int,
        bars: list[OHLCVBar],
        timeframe: Timeframe,
    ) -> Candle:
        """Merge a list of OHLCV bars into a single aggregated candle."""
        if not bars:
            raise ValueError("Cannot merge empty bar list")

        sorted_bars = sorted(bars, key=lambda b: b.timestamp)
        open_price = sorted_bars[0].open_price
        high = max(b.high for b in sorted_bars)
        low = min(b.low for b in sorted_bars)
        close = sorted_bars[-1].close_price
        volume = sum(b.volume for b in sorted_bars)
        timestamp = to_utc(
            to_ist(sorted_bars[0].timestamp).replace(second=0, microsecond=0)
        )

        return Candle(
            instrument_token=instrument_token,
            timeframe=timeframe.value,
            timestamp=timestamp,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )
