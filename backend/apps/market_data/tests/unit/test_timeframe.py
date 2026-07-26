from __future__ import annotations

from decimal import Decimal

import pytest

from apps.market_data.domain.value_objects import Timeframe


class TestTimeframeEnum:
    def test_from_string_valid(self) -> None:
        assert Timeframe.from_string("15min") == Timeframe.MINUTE_15
        assert Timeframe.from_string("1D") == Timeframe.DAY_1
        assert Timeframe.from_string("1hr") == Timeframe.HOUR_1

    def test_from_string_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown timeframe"):
            Timeframe.from_string("invalid")

    def test_is_intraday(self) -> None:
        assert Timeframe.MINUTE_1.is_intraday
        assert Timeframe.MINUTE_15.is_intraday
        assert Timeframe.HOUR_1.is_intraday
        assert not Timeframe.DAY_1.is_intraday
        assert not Timeframe.WEEK_1.is_intraday

    def test_cache_ttl_seconds(self) -> None:
        assert Timeframe.MINUTE_1.cache_ttl_seconds == 30
        assert Timeframe.MINUTE_15.cache_ttl_seconds == 300
        assert Timeframe.DAY_1.cache_ttl_seconds == 7200

    def test_all_timeframes_have_cache_ttl(self) -> None:
        for tf in Timeframe:
            ttl = tf.cache_ttl_seconds
            assert isinstance(ttl, int)
            assert ttl > 0
