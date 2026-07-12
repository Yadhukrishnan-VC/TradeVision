"""
Tests for core.services — logger init, correlation ID bind/clear.
"""

from core.services import BaseService


class TestBaseService:

    def test_logger_init(self) -> None:
        svc = BaseService()
        assert svc.logger is not None

    def test_bind_and_clear_correlation(self) -> None:
        svc = BaseService()
        cid = svc.bind_correlation()
        assert isinstance(cid, str)
        assert len(cid) > 0
        svc.clear_correlation()

    def test_bind_custom_correlation(self) -> None:
        svc = BaseService()
        cid = svc.bind_correlation("custom-id-123")
        assert cid == "custom-id-123"
        svc.clear_correlation()
