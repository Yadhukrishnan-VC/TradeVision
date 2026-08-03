from __future__ import annotations

import json

import pytest

from apps.ingestion.application.services import TradingViewPayloadParser
from apps.ingestion.domain.exceptions import MalformedPayloadError


class TestTradingViewPayloadParser:
    @pytest.fixture
    def parser(self) -> TradingViewPayloadParser:
        return TradingViewPayloadParser()

    def test_parse_valid_json(self, parser: TradingViewPayloadParser) -> None:
        body = json.dumps({
            "ticker": "RELIANCE",
            "close": 2500.50,
            "time": "2025-03-10T10:00:00Z",
            "volume": 100000,
        }).encode("utf-8")

        result = parser.parse(body)
        assert result["ticker"] == "RELIANCE"
        assert result["close"] == 2500.50
        assert result["time"] == "2025-03-10T10:00:00Z"

    def test_parse_missing_required_fields(self, parser: TradingViewPayloadParser) -> None:
        body = json.dumps({"ticker": "RELIANCE"}).encode("utf-8")
        with pytest.raises(MalformedPayloadError, match="Missing required fields"):
            parser.parse(body)

    def test_parse_empty_body(self, parser: TradingViewPayloadParser) -> None:
        with pytest.raises(MalformedPayloadError):
            parser.parse(b"")

    def test_parse_invalid_utf8(self, parser: TradingViewPayloadParser) -> None:
        with pytest.raises(MalformedPayloadError, match="not valid UTF-8"):
            parser.parse(b"\xff\xfe\x00\x01")

    def test_parse_malformed_json(self, parser: TradingViewPayloadParser) -> None:
        body = b"this is not json at all"
        with pytest.raises(MalformedPayloadError, match="Missing required fields"):
            parser.parse(body)

    def test_normalise_symbol_field(self, parser: TradingViewPayloadParser) -> None:
        body = json.dumps({
            "symbol": "TCS",
            "close": 3500.00,
            "time": "2025-03-10T10:00:00Z",
        }).encode("utf-8")

        result = parser.parse(body)
        assert result["ticker"] == "TCS"

    def test_normalise_price_field(self, parser: TradingViewPayloadParser) -> None:
        body = json.dumps({
            "ticker": "INFY",
            "price": 1800.00,
            "time": "2025-03-10T10:00:00Z",
        }).encode("utf-8")

        result = parser.parse(body)
        assert result["close"] == 1800.00

    def test_case_insensitive_keys(self, parser: TradingViewPayloadParser) -> None:
        body = json.dumps({
            "TICKER": "HDFCBANK",
            "Close": 1600.00,
            "TIME": "2025-03-10T10:00:00Z",
        }).encode("utf-8")

        result = parser.parse(body)
        assert result["ticker"] == "HDFCBANK"
        assert result["close"] == 1600.00

    def test_extra_fields_preserved(self, parser: TradingViewPayloadParser) -> None:
        body = json.dumps({
            "ticker": "SBIN",
            "close": 800.00,
            "time": "2025-03-10T10:00:00Z",
            "strategy": {
                "position_size": "50",
                "market_position": "long",
            },
        }).encode("utf-8")

        result = parser.parse(body)
        assert result["strategy"]["position_size"] == "50"
