"""
Tests for BaseTask — correlation ID, timing, retry constants.
"""

from core.tasks.base import BaseTask


class TestBaseTask:
    """Test BaseTask class attributes and helpers."""

    def test_retry_constants(self) -> None:
        assert BaseTask.max_retries == 3
        assert BaseTask.default_retry_delay == 60

    def test_idempotency_key(self) -> None:
        key = BaseTask.idempotency_key("ingest", "RELIANCE", "2024-03-17")
        assert key == "ingest:RELIANCE:2024-03-17"

    def test_idempotency_key_single_part(self) -> None:
        key = BaseTask.idempotency_key("single")
        assert key == "single"
