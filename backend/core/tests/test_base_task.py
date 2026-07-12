"""
Tests for core/tasks/base.py — BaseTask retry constants and helpers.
"""

import pytest

from core.tasks.base import (
    AI_MAX_RETRIES,
    AI_RETRY_DELAY,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RETRY_BACKOFF,
    DEFAULT_RETRY_DELAY,
    INGESTION_MAX_RETRIES,
    INGESTION_RETRY_DELAY,
    NOTIFICATION_MAX_RETRIES,
    NOTIFICATION_RETRY_DELAY,
    BaseTask,
)


class TestRetryConstants:
    """Retry constants must have specific values matching the architecture spec."""

    def test_default_max_retries_is_three(self) -> None:
        assert DEFAULT_MAX_RETRIES == 3

    def test_default_retry_delay_is_sixty(self) -> None:
        assert DEFAULT_RETRY_DELAY == 60

    def test_default_retry_backoff_is_two(self) -> None:
        assert DEFAULT_RETRY_BACKOFF == 2.0

    def test_ai_max_retries_is_five(self) -> None:
        assert AI_MAX_RETRIES == 5

    def test_ai_retry_delay_is_higher_than_default(self) -> None:
        assert AI_RETRY_DELAY > DEFAULT_RETRY_DELAY

    def test_ingestion_max_retries_is_three(self) -> None:
        assert INGESTION_MAX_RETRIES == 3

    def test_ingestion_retry_delay_is_shorter_than_default(self) -> None:
        assert INGESTION_RETRY_DELAY < DEFAULT_RETRY_DELAY

    def test_notification_max_retries_is_higher_than_default(self) -> None:
        assert NOTIFICATION_MAX_RETRIES > DEFAULT_MAX_RETRIES

    def test_notification_retry_delay_is_short(self) -> None:
        assert NOTIFICATION_RETRY_DELAY < DEFAULT_RETRY_DELAY

    def test_all_retry_values_are_positive(self) -> None:
        values = [
            DEFAULT_MAX_RETRIES,
            DEFAULT_RETRY_DELAY,
            DEFAULT_RETRY_BACKOFF,
            AI_MAX_RETRIES,
            AI_RETRY_DELAY,
            INGESTION_MAX_RETRIES,
            INGESTION_RETRY_DELAY,
            NOTIFICATION_MAX_RETRIES,
            NOTIFICATION_RETRY_DELAY,
        ]
        for v in values:
            assert v > 0, f"Expected positive value, got {v}"


class TestBaseTaskIdempotencyKey:
    """make_idempotency_key() must produce deterministic, namespaced keys."""

    def test_single_part(self) -> None:
        key = BaseTask.make_idempotency_key("RELIANCE")
        assert key == "idempotency:RELIANCE"

    def test_multiple_parts_joined_with_colon(self) -> None:
        key = BaseTask.make_idempotency_key("RELIANCE", "price_movement", "2024-01-15")
        assert key == "idempotency:RELIANCE:price_movement:2024-01-15"

    def test_key_starts_with_namespace(self) -> None:
        key = BaseTask.make_idempotency_key("any", "value")
        assert key.startswith("idempotency:")

    def test_same_inputs_produce_same_key(self) -> None:
        key_a = BaseTask.make_idempotency_key("INFY", "volume_spike", "09:30")
        key_b = BaseTask.make_idempotency_key("INFY", "volume_spike", "09:30")
        assert key_a == key_b

    def test_different_inputs_produce_different_keys(self) -> None:
        key_a = BaseTask.make_idempotency_key("INFY", "price_movement")
        key_b = BaseTask.make_idempotency_key("RELIANCE", "price_movement")
        assert key_a != key_b

    def test_non_string_parts_are_coerced(self) -> None:
        key = BaseTask.make_idempotency_key("SYMBOL", "123", "3.14")
        assert "123" in key
        assert "3.14" in key

    def test_is_static_method(self) -> None:
        """make_idempotency_key must be callable without a task instance."""
        key = BaseTask.make_idempotency_key("test")
        assert isinstance(key, str)


class TestBaseTaskIsAbstract:
    """BaseTask must declare itself abstract so Celery does not auto-register it."""

    def test_abstract_attribute_is_true(self) -> None:
        assert BaseTask.abstract is True
