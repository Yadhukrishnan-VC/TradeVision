"""
Tests for core.services — logger init, context bind/clear, correlation ID generation.
"""

from core.services import BaseService


class TestBaseService:

    def test_logger_init(self) -> None:
        svc = BaseService()
        assert svc._logger is not None

    def test_bind_and_clear_context(self) -> None:
        svc = BaseService()
        svc.bind_context(symbol="RELIANCE", correlation_id="test-123")
        svc.clear_context()

    def test_generate_correlation_id(self) -> None:
        svc = BaseService()
        cid = svc.generate_correlation_id()
        assert isinstance(cid, str)
        assert len(cid) > 0
