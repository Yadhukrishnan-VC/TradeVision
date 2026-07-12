"""
Tests for core.middleware — correlation ID header passthrough, UUID generation, request logging.
"""

from unittest.mock import MagicMock

from core.middleware import CorrelationIDMiddleware, RequestLoggingMiddleware, CORRELATION_ID_HEADER


class _FakeResponse:
    """Minimal response mock that supports header dict operations."""

    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self._headers: dict[str, str] = {}

    def __setitem__(self, key: str, value: str) -> None:
        self._headers[key] = value

    def __getitem__(self, key: str) -> str:
        return self._headers[key]

    def __contains__(self, key: str) -> bool:
        return key in self._headers


class TestCorrelationIDMiddleware:

    def _make_request(self, headers: dict | None = None) -> MagicMock:
        request = MagicMock()
        request.headers = headers or {}
        request.path = "/test"
        request.method = "GET"
        return request

    def test_generates_uuid_when_no_header(self) -> None:
        def view(request):
            return _FakeResponse()

        mw = CorrelationIDMiddleware(view)
        request = self._make_request()
        response = mw(request)
        assert CORRELATION_ID_HEADER in response

    def test_passthrough_existing_header(self) -> None:
        def view(request):
            return _FakeResponse()

        mw = CorrelationIDMiddleware(view)
        request = self._make_request({CORRELATION_ID_HEADER: "my-custom-id"})
        response = mw(request)
        assert response[CORRELATION_ID_HEADER] == "my-custom-id"


class TestRequestLoggingMiddleware:

    def _make_request(self, headers: dict | None = None) -> MagicMock:
        request = MagicMock()
        request.headers = headers or {}
        request.path = "/test"
        request.method = "GET"
        return request

    def test_logs_request(self) -> None:
        def view(request):
            return _FakeResponse(200)

        mw = RequestLoggingMiddleware(view)
        request = self._make_request()
        response = mw(request)
        assert response.status_code == 200
