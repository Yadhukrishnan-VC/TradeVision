from __future__ import annotations

import pytest

from apps.common.domain.exceptions import DomainError, NotFoundError
from apps.common.domain.result import Result


class TestResult:
    def test_ok_creates_success_result(self) -> None:
        result: Result[int] = Result.ok(42)
        assert result.is_success is True
        assert result.is_failure is False
        assert result.value == 42
        assert result.error is None

    def test_fail_creates_failure_result(self) -> None:
        error = DomainError("something went wrong")
        result: Result[int] = Result.fail(error)
        assert result.is_success is False
        assert result.is_failure is True
        assert result.value is None
        assert result.error is error

    def test_unwrap_on_success_returns_value(self) -> None:
        result: Result[str] = Result.ok("hello")
        assert result.unwrap() == "hello"

    def test_unwrap_on_failure_raises_error(self) -> None:
        error = NotFoundError("not found")
        result: Result[str] = Result.fail(error)
        with pytest.raises(NotFoundError, match="not found"):
            result.unwrap()

    def test_ok_with_none_value(self) -> None:
        result: Result[None] = Result.ok(None)
        assert result.is_success is True
        assert result.value is None

    def test_fail_with_subclass_error(self) -> None:
        error = NotFoundError("missing", code="user_not_found")
        result: Result[None] = Result.fail(error)
        assert result.is_failure is True
        assert isinstance(result.error, NotFoundError)

    def test_representation(self) -> None:
        ok_result: Result[int] = Result.ok(1)
        assert repr(ok_result) == "Result.ok(1)"
        err = DomainError("fail")
        fail_result: Result[int] = Result.fail(err)
        assert repr(fail_result) == "Result.fail(DomainError('fail'))"
