"""
Tests for core.responses — to_dict() shape for all response types; frozen immutability.
"""

import pytest

from core.responses import (
    ErrorResponse,
    HealthResponse,
    PaginatedResponse,
    ServiceHealthStatus,
    SuccessResponse,
    ValidationErrorResponse,
)


class TestSuccessResponse:

    def test_to_dict_shape(self) -> None:
        r = SuccessResponse(data={"symbol": "RELIANCE"})
        d = r.to_dict()
        assert d["data"]["symbol"] == "RELIANCE"
        assert d["message"] == "success"

    def test_frozen(self) -> None:
        r = SuccessResponse(data="x")
        with pytest.raises(AttributeError):
            r.data = "y"


class TestErrorResponse:

    def test_to_dict_shape(self) -> None:
        r = ErrorResponse(message="Not found", status_code=404)
        d = r.to_dict()
        assert d["error"]["message"] == "Not found"
        assert d["error"]["status_code"] == 404

    def test_with_error_code(self) -> None:
        r = ErrorResponse(message="err", error_code="E001")
        d = r.to_dict()
        assert d["error"]["code"] == "E001"


class TestValidationErrorResponse:

    def test_to_dict_shape(self) -> None:
        r = ValidationErrorResponse(errors={"email": ["Invalid"]})
        d = r.to_dict()
        assert d["error"]["status_code"] == 422
        assert d["error"]["detail"]["email"] == ["Invalid"]


class TestPaginatedResponse:

    def test_to_dict_shape(self) -> None:
        r = PaginatedResponse(count=10, next="url2", previous=None, results=[1, 2])
        d = r.to_dict()
        assert d["count"] == 10
        assert d["next"] == "url2"
        assert d["previous"] is None
        assert d["results"] == [1, 2]


class TestServiceHealthStatus:

    def test_to_dict_shape(self) -> None:
        s = ServiceHealthStatus(status="healthy", latency_ms=12.5)
        d = s.to_dict()
        assert d["status"] == "healthy"
        assert d["latency_ms"] == 12.5

    def test_omits_empty_fields(self) -> None:
        s = ServiceHealthStatus(status="healthy")
        d = s.to_dict()
        assert "latency_ms" not in d
        assert "message" not in d


class TestHealthResponse:

    def test_to_dict_shape(self) -> None:
        h = HealthResponse(
            status="healthy",
            checks={"db": ServiceHealthStatus(status="healthy")},
            version="0.1.0",
        )
        d = h.to_dict()
        assert d["status"] == "healthy"
        assert d["version"] == "0.1.0"
        assert d["checks"]["db"]["status"] == "healthy"
