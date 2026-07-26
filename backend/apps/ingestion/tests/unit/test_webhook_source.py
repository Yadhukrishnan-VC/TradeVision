from __future__ import annotations

import pytest

from apps.ingestion.domain.value_objects import WebhookSource


class TestWebhookSource:
    def test_from_string_valid(self) -> None:
        assert WebhookSource.from_string("tradingview") == WebhookSource.TRADINGVIEW
        assert WebhookSource.from_string("chartink") == WebhookSource.CHARTINK

    def test_from_string_case_insensitive(self) -> None:
        assert WebhookSource.from_string("TRADINGVIEW") == WebhookSource.TRADINGVIEW
        assert WebhookSource.from_string("Chartink") == WebhookSource.CHARTINK

    def test_from_string_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown webhook source"):
            WebhookSource.from_string("unknown")

    def test_values(self) -> None:
        assert WebhookSource.TRADINGVIEW.value == "tradingview"
        assert WebhookSource.CHARTINK.value == "chartink"

    def test_all_sources_covered(self) -> None:
        sources = {s.value for s in WebhookSource}
        assert "tradingview" in sources
        assert "chartink" in sources
