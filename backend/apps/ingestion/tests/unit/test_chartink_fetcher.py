from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.ingestion.application.chartink_scan_fetcher import ChartinkScanFetcher
from core.exceptions import DataIngestionError


class TestChartinkScanFetcher:
    @pytest.fixture
    def fetcher(self) -> ChartinkScanFetcher:
        return ChartinkScanFetcher(
            scan_name="test_scan",
            scan_id=12345,
        )

    def test_extract_symbols_from_nsecode(self, fetcher: ChartinkScanFetcher) -> None:
        data = {"data": [{"nsecode": "RELIANCE"}, {"nsecode": "TCS"}]}
        symbols = fetcher._extract_symbols(data)
        assert symbols == ["RELIANCE", "TCS"]

    def test_extract_symbols_from_symbol_field(self, fetcher: ChartinkScanFetcher) -> None:
        data = {"stocks": [{"symbol": "INFY"}, {"symbol": "WIPRO"}]}
        symbols = fetcher._extract_symbols(data)
        assert symbols == ["INFY", "WIPRO"]

    def test_extract_symbols_deduplicates(self, fetcher: ChartinkScanFetcher) -> None:
        data = {"data": [{"nsecode": "RELIANCE"}, {"nsecode": "RELIANCE"}]}
        symbols = fetcher._extract_symbols(data)
        assert symbols == ["RELIANCE"]

    def test_extract_symbols_empty_response(self, fetcher: ChartinkScanFetcher) -> None:
        symbols = fetcher._extract_symbols({})
        assert symbols == []

    def test_extract_symbols_string_fallback(self, fetcher: ChartinkScanFetcher) -> None:
        data = {"result": [{"ticker": "SBIN"}]}
        symbols = fetcher._extract_symbols(data)
        assert symbols == ["SBIN"]

    @patch("apps.ingestion.application.chartink_scan_fetcher.requests")
    def test_execute_scan_success(self, mock_requests: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"nsecode": "RELIANCE"}]}
        mock_response.raise_for_status.return_value = None
        mock_requests.post.return_value = mock_response

        fetcher = ChartinkScanFetcher(scan_name="scan1", scan_id=1)
        result = fetcher._execute_scan()
        assert result["scan_name"] == "scan1"
        assert result["symbols"] == ["RELIANCE"]

    @patch("apps.ingestion.application.chartink_scan_fetcher.requests")
    def test_execute_scan_http_error(self, mock_requests: MagicMock) -> None:
        from requests.exceptions import RequestException

        mock_requests.post.side_effect = RequestException("Timeout")
        fetcher = ChartinkScanFetcher(scan_name="scan1", scan_id=1)

        with pytest.raises(DataIngestionError, match="Chartink scan HTTP error"):
            fetcher._execute_scan()
