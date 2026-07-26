from __future__ import annotations

from enum import Enum


class Timeframe(str, Enum):
    """Candle aggregation interval as used throughout Trading Core.

    Maps human-readable interval names to their internal string
    representation. Every value corresponds to a valid ``interval``
    argument for ``BaseMarketDataProvider.fetch()``.
    """

    MINUTE_1 = "1min"
    MINUTE_3 = "3min"
    MINUTE_5 = "5min"
    MINUTE_10 = "10min"
    MINUTE_15 = "15min"
    MINUTE_30 = "30min"
    HOUR_1 = "1hr"
    HOUR_2 = "2hr"
    HOUR_4 = "4hr"
    DAY_1 = "1D"
    WEEK_1 = "1W"
    MONTH_1 = "1M"

    @classmethod
    def from_string(cls, value: str) -> Timeframe:
        """Parse a timeframe string, raising ``ValueError`` on invalid input.

        Args:
            value: Raw timeframe string (e.g. ``"15min"``, ``"1D"``).

        Returns:
            The matching ``Timeframe`` member.

        Raises:
            ValueError: If ``value`` does not match any known timeframe.
        """
        try:
            return cls(value)
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"Unknown timeframe {value!r}. Valid: {valid}")

    @property
    def is_intraday(self) -> bool:
        """Return ``True`` for timeframes shorter than one trading day."""
        return self in (
            Timeframe.MINUTE_1,
            Timeframe.MINUTE_3,
            Timeframe.MINUTE_5,
            Timeframe.MINUTE_10,
            Timeframe.MINUTE_15,
            Timeframe.MINUTE_30,
            Timeframe.HOUR_1,
            Timeframe.HOUR_2,
            Timeframe.HOUR_4,
        )

    @property
    def cache_ttl_seconds(self) -> int:
        """Recommended Redis cache TTL in seconds for this timeframe.

        Longer timeframes are cached longer because they change less
        frequently.
        """
        ttl_map: dict[Timeframe, int] = {
            Timeframe.MINUTE_1: 30,
            Timeframe.MINUTE_3: 60,
            Timeframe.MINUTE_5: 120,
            Timeframe.MINUTE_10: 240,
            Timeframe.MINUTE_15: 300,
            Timeframe.MINUTE_30: 600,
            Timeframe.HOUR_1: 1200,
            Timeframe.HOUR_2: 2400,
            Timeframe.HOUR_4: 3600,
            Timeframe.DAY_1: 7200,
            Timeframe.WEEK_1: 14400,
            Timeframe.MONTH_1: 28800,
        }
        return ttl_map[self]
