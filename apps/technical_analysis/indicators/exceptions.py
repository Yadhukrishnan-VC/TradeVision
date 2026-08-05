from __future__ import annotations

from typing import Any


class IndicatorError(Exception):
    """Base exception for all indicator errors."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        indicator_type: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.indicator_name = indicator_name
        self.indicator_type = indicator_type
        self.cause = cause

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.indicator_name:
            parts.append(f"indicator={self.indicator_name}")
        if self.indicator_type:
            parts.append(f"type={self.indicator_type}")
        if self.cause:
            parts.append(f"cause={self.cause}")
        return " | ".join(parts)


class CalculationError(IndicatorError):
    """Raised when indicator calculation fails."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        indicator_type: str | None = None,
        cause: BaseException | None = None,
        input_length: int | None = None,
        required_length: int | None = None,
    ) -> None:
        super().__init__(message, indicator_name, indicator_type, cause)
        self.input_length = input_length
        self.required_length = required_length


class InsufficientDataError(CalculationError):
    """Raised when there's insufficient data for calculation."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        indicator_type: str | None = None,
        required_length: int | None = None,
        provided_length: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        message = f"Insufficient data: {message}"
        super().__init__(message, indicator_name, indicator_type, cause, provided_length, required_length)
        self.required_length = required_length
        self.provided_length = provided_length


class InvalidDataError(CalculationError):
    """Raised when input data is invalid."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        indicator_type: str | None = None,
        invalid_indices: list[int] | None = None,
        invalid_values: list[Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, indicator_name, indicator_type, cause)
        self.invalid_indices = invalid_indices or []
        self.invalid_values = invalid_values or []


class InvalidParameterError(IndicatorError):
    """Raised when indicator parameters are invalid."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        indicator_type: str | None = None,
        parameter_name: str | None = None,
        parameter_value: Any = None,
        valid_range: tuple[Any, Any] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        message = f"Invalid parameter: {message}"
        super().__init__(message, indicator_name, indicator_type, cause)
        self.parameter_name = parameter_name
        self.parameter_value = parameter_value
        self.valid_range = valid_range


class IndicatorNotFoundError(IndicatorError):
    """Raised when requested indicator is not registered."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        available_indicators: list[str] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, indicator_name, cause=cause)
        self.available_indicators = available_indicators or []


class IndicatorAlreadyRegisteredError(IndicatorError):
    """Raised when attempting to register an already registered indicator."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        existing_class: type | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, indicator_name, cause=cause)
        self.existing_class = existing_class


class InvalidConfigurationError(IndicatorError):
    """Raised when indicator configuration is invalid."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        indicator_type: str | None = None,
        missing_parameters: list[str] | None = None,
        invalid_parameters: dict[str, str] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, indicator_name, indicator_type, cause)
        self.missing_parameters = missing_parameters or []
        self.invalid_parameters = invalid_parameters or {}


class CalculationOverflowError(CalculationError):
    """Raised when calculation results in overflow/underflow."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        indicator_type: str | None = None,
        operation: str | None = None,
        operand_values: list[float] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, indicator_name, indicator_type, cause)
        self.operation = operation
        self.operand_values = operand_values or []


class InsufficientHistoryError(InsufficientDataError):
    """Raised when historical data is insufficient for lookback periods."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        indicator_type: str | None = None,
        lookback_period: int | None = None,
        available_periods: int | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(
            message, indicator_name, indicator_type, lookback_period, available_periods, cause
        )
        self.lookback_period = lookback_period
        self.available_periods = available_periods


class DivisionByZeroError(CalculationError):
    """Raised when calculation would result in division by zero."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        indicator_type: str | None = None,
        denominator_expression: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, indicator_name, indicator_type, cause)
        self.denominator_expression = denominator_expression


class InvalidOHLCVError(InvalidDataError):
    """Raised when OHLCV data is invalid."""

    def __init__(
        self,
        message: str,
        indicator_name: str | None = None,
        invalid_indices: list[int] | None = None,
        invalid_fields: list[str] | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, indicator_name, indicator_type=None, invalid_indices=invalid_indices, cause=cause)
        self.invalid_fields = invalid_fields or []


class InsufficientHistoryForIndicatorError(InsufficientHistoryError):
    """Raised when specific indicator requires more history than available."""

    def __init__(
        self,
        indicator_name: str,
        required_periods: int,
        available_periods: int,
        cause: BaseException | None = None,
    ) -> None:
        message = f"Insufficient history for {indicator_name}: requires {required_periods}, got {available_periods}"
        super().__init__(
            message,
            indicator_name=indicator_name,
            indicator_type=None,
            lookback_period=required_periods,
            available_periods=available_periods,
            cause=cause,
        )