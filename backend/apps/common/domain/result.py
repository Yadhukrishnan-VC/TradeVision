from __future__ import annotations

from typing import Generic, TypeVar

from apps.common.domain.exceptions import DomainError

T = TypeVar("T")


class Result(Generic[T]):
    """A wrapper that represents either a success value or a failure error.

    Use this to return expected business failures from use cases without
    raising exceptions for control flow.
    """

    def __init__(self, is_success: bool, value: T | None = None, error: DomainError | None = None) -> None:
        self._is_success = is_success
        self._value = value
        self._error = error

    @property
    def is_success(self) -> bool:
        return self._is_success

    @property
    def is_failure(self) -> bool:
        return not self._is_success

    @property
    def value(self) -> T | None:
        return self._value

    @property
    def error(self) -> DomainError | None:
        return self._error

    @classmethod
    def ok(cls, value: T) -> Result[T]:
        """Create a successful result wrapping the given value."""
        return cls(is_success=True, value=value)

    @classmethod
    def fail(cls, error: DomainError) -> Result[T]:
        """Create a failure result wrapping the given domain error."""
        return cls(is_success=False, error=error)

    def unwrap(self) -> T:
        """Return the wrapped value or raise the domain error.

        Returns:
            The success value.

        Raises:
            DomainError: If this result represents a failure.
        """
        if self.is_failure and self._error is not None:
            raise self._error
        return self._value  # type: ignore[return-value]

    def __repr__(self) -> str:
        if self._is_success:
            return f"Result.ok({self._value!r})"
        return f"Result.fail({self._error!r})"
