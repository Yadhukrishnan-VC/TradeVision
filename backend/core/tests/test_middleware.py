"""
Tests for core.middleware — correlation ID header passthrough, UUID generation, request logging.
"""

from unittest.mock import MagicMock

from core.middleware import CorrelationIDMiddleware, CORRELATION_HEADER


class TestCorrelationIDMiddleware:

    def _make_request(self, headers: dict | None = None) -> MagicMock:
        request = MagicMock()
        request.headers = headers or {}
        request.path = "/test"
        request.method = "GET"
        return request

    def test_generates_uuid_when_no_header(self) -> None:
        def view(request):
            return MagicMock()

        mw = CorrelationIDMiddleware(view)
        request = self._make_request()
        response = mw(request)
        assert CORRELATION_HEADER in response

    def test_passthrough_existing_header(self) -> None:
        def view(request):
            return MagicMock()

        mw = CorrelationIDMiddleware(view)
        request = self._make_request({CORRELATION_HEADER: "my-custom-id"})
        response = mw(request)
        assert response[CORRELATION_HEADER] == "my-custom-id"
