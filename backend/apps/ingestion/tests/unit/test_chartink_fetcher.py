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

        # The production module raises through ``except requests.RequestException``,
        # so the patched module-level ``requests`` must expose the real exception
        # class for that except clause to match.
        mock_requests.RequestException = RequestException
        mock_requests.post.side_effect = RequestException("Timeout")
        fetcher = ChartinkScanFetcher(scan_name="scan1", scan_id=1)

        with pytest.raises(DataIngestionError, match="Chartink scan HTTP error"):
            fetcher._execute_scan()






class TestPollChartinkScansScheduled:
    """Tests for poll_chartink_scans_scheduled wrapper task.

    Proves:
      1. No-op when SCAN_ID is 0 / unset.
      2. Forwards to poll_chartink_scans with the right args when SCAN_ID is set.
    """

    @patch('django.conf.settings')
    def test_no_op_when_scan_id_is_zero(self, mock_settings) -> None:
        mock_settings.SCAN_ID = 0
        mock_settings.SHARED_SECRET = None

        from apps.ingestion.infrastructure.tasks import poll_chartink_scans_scheduled

        result = poll_chartink_scans_scheduled()
        assert result == {"polled": False, "reason": "SCAN_ID is 0 or unset"}

    @patch('django.conf.settings')
    def test_forwards_when_scan_id_is_set(self, mock_settings) -> None:
        mock_settings.SCAN_ID = 42
        mock_settings.SHARED_SECRET = "my-secret"

        with patch('apps.ingestion.infrastructure.tasks.poll_chartink_scans.s') as mock_dispatch:
            from apps.ingestion.infrastructure.tasks import poll_chartink_scans_scheduled

            poll_chartink_scans_scheduled()

            mock_dispatch.assert_called_once_with(
                scan_name='scan-42',
                scan_id=42,
                shared_secret='my-secret',
            )
