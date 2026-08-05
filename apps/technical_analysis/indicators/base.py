from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Generic, Sequence, TypeVar
from uuid import uuid4

from apps.technical_analysis.indicators.exceptions import (
    CalculationError,
    InsufficientDataError,
    InvalidDataError,
    InvalidParameterError,
)


TResult = TypeVar("TResult")
IndicatorData = Sequence["OHLCV"]


class IndicatorType(Enum):
    """Enumeration of indicator categories."""

    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class OHLCV:
    """Immutable OHLCV data point."""

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.open < self.low or self.open > self.high:
            raise ValueError("open must be between low and high")
        if self.close < self.low or self.close > self.high:
            raise ValueError("close must be between low and high")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")

    @property
    def typical_price(self) -> Decimal:
        """Typical price = (H + L + C) / 3."""
        return (self.high + self.low + self.close) / Decimal("3")

    @property
    def weighted_close(self) -> Decimal:
        """Weighted close = (H + L + 2*C) / 4."""
        return (self.high + self.low + self.close * Decimal("2")) / Decimal("4")

    @property
    def median_price(self) -> Decimal:
        """Median price = (H + L) / 2."""
        return (self.high + self.low) / Decimal("2")


@dataclass(frozen=True, slots=True)
class IndicatorConfig:
    """Immutable indicator configuration."""

    name: str
    indicator_type: IndicatorType
    parameters: dict[str, Any] = field(default_factory=dict)
    required_data_points: int = 1

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name cannot be empty")
        if self.required_data_points < 1:
            raise ValueError("required_data_points must be >= 1")
        if not isinstance(self.parameters, dict):
            raise ValueError("parameters must be a dict")

    def get_parameter(self, name: str, default: Any = None) -> Any:
        """Get parameter with default."""
        return self.parameters.get(name, default)

    def get_int_parameter(self, name: str, default: int | None = None) -> int:
        """Get integer parameter with validation."""
        value = self.parameters.get(name, default)
        if value is None:
            if default is None:
                raise InvalidParameterError(f"Required parameter '{name}' not provided", parameter_name=name)
            return default
        try:
            return int(value)
        except (ValueError, TypeError) as e:
            raise InvalidParameterError(
                f"Parameter '{name}' must be an integer",
                parameter_name=name,
                parameter_value=value,
            ) from e

    def get_decimal_parameter(self, name: str, default: Decimal | None = None) -> Decimal:
        """Get Decimal parameter with validation."""
        value = self.parameters.get(name, default)
        if value is None:
            if default is None:
                raise InvalidParameterError(f"Required parameter '{name}' not provided", parameter_name=name)
            return default
        try:
            return Decimal(str(value))
        except (ValueError, TypeError) as e:
            raise InvalidParameterError(
                f"Parameter '{name}' must be a valid decimal",
                parameter_name=name,
                parameter_value=value,
            ) from e


@dataclass(frozen=True, slots=True)
class IndicatorResult(Generic[TResult]):
    """Immutable indicator calculation result."""

    name: str
    indicator_type: IndicatorType
    timestamp: datetime
    value: TResult
    parameters: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    calculation_id: str = field(default_factory=lambda: uuid4().hex[:8])

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

    def get_value(self, index: int = 0) -> Decimal:
        """Extract Decimal value from result."""
        if isinstance(self.value, Decimal):
            return self.value
        if isinstance(self.value, tuple):
            if index < len(self.value):
                return self.value[index]
            raise IndexError(f"Index {index} out of range for tuple of length {len(self.value)}")
        if isinstance(self.value, (int, float)):
            return Decimal(str(self.value))
        raise TypeError(f"Cannot extract Decimal from {type(self.value)}")

    def as_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        result = {
            "name": self.name,
            "type": self.indicator_type.value,
            "timestamp": self.timestamp.isoformat(),
            "value": self._serialize_value(self.value),
            "parameters": self.parameters,
            "metadata": self.metadata,
            "calculation_id": self.calculation_id,
        }
        return result

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, tuple):
            return tuple(self._serialize_value(v) for v in value)
        if isinstance(value, (list, set)):
            return [self._serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        return value


class BaseIndicator(ABC, Generic[TResult]):
    """Abstract base class for all technical indicators."""

    def __init__(self, config: IndicatorConfig) -> None:
        self._config = config
        self._validate_config()

    @property
    def config(self) -> IndicatorConfig:
        """Get indicator configuration."""
        return self._config

    @property
    def name(self) -> str:
        """Get indicator name."""
        return self._config.name

    @property
    def indicator_type(self) -> IndicatorType:
        """Get indicator type."""
        return self._config.indicator_type

    @property
    def required_data_points(self) -> int:
        """Get minimum required data points."""
        return self._config.required_data_points

    @abstractmethod
    def _calculate(self, data: IndicatorData) -> list[IndicatorResult[TResult]]:
        """Perform the actual calculation. Must be implemented by subclasses."""

    @abstractmethod
    def _validate_config(self) -> None:
        """Validate indicator-specific configuration."""

    def _validate_data(self, data: IndicatorData) -> None:
        """Validate input data."""
        if not data:
            raise InvalidDataError("Input data cannot be empty", indicator_name=self.name)
        if len(data) < self.required_data_points:
            raise InsufficientDataError(
                f"Requires at least {self.required_data_points} data points, got {len(data)}",
                indicator_name=self.name,
                required_length=self.required_data_points,
                provided_length=len(data),
            )

        for i, ohlcv in enumerate(data):
            if not isinstance(ohlcv, OHLCV):
                raise InvalidDataError(
                    f"Element at index {i} is not OHLCV",
                    indicator_name=self.name,
                    invalid_indices=[i],
                )

            if i > 0:
                prev = data[i - 1]
                if ohlcv.timestamp <= prev.timestamp:
                    raise InvalidDataError(
                        f"Timestamps must be strictly increasing (index {i})",
                        indicator_name=self.name,
                        invalid_indices=[i - 1, i],
                    )

    def calculate(self, data: IndicatorData) -> list[IndicatorResult[TResult]]:
        """Calculate indicator values for all data points."""
        self._validate_data(data)
        try:
            return self._calculate(data)
        except (InsufficientDataError, InvalidDataError, InvalidParameterError):
            raise
        except ZeroDivisionError as e:
            raise CalculationError(
                "Division by zero in calculation",
                indicator_name=self.name,
                indicator_type=self.indicator_type.value,
                cause=e,
            ) from e
        except (OverflowError, ArithmeticError) as e:
            raise CalculationError(
                f"Arithmetic error: {e}",
                indicator_name=self.name,
                indicator_type=self.indicator_type.value,
                cause=e,
            ) from e
        except Exception as e:
            raise CalculationError(
                f"Calculation failed: {e}",
                indicator_name=self.name,
                indicator_type=self.indicator_type.value,
                cause=e,
            ) from e

    def get_latest(self, data: IndicatorData) -> IndicatorResult[TResult] | None:
        """Get the most recent indicator value."""
        try:
            results = self.calculate(data)
            return results[-1] if results else None
        except InsufficientDataError:
            return None


class SingleValueIndicator(BaseIndicator[Decimal]):
    """Base class for indicators producing a single Decimal value per period."""

    @abstractmethod
    def _calculate_single(self, data: IndicatorData, index: int) -> Decimal:
        """Calculate indicator value for a single index."""

    def _calculate(self, data: IndicatorData) -> list[IndicatorResult[Decimal]]:
        results = []
        start = self.required_data_points - 1
        for i in range(start, len(data)):
            value = self._calculate_single(data, i)
            results.append(
                IndicatorResult(
                    name=self.name,
                    indicator_type=self.indicator_type,
                    timestamp=data[i].timestamp,
                    value=value,
                    parameters=self.config.parameters,
                )
            )
        return results


class MultiValueIndicator(BaseIndicator[tuple[Decimal, ...]]):
    """Base class for indicators producing multiple values per period."""

    @property
    @abstractmethod
    def output_names(self) -> tuple[str, ...]:
        """Names of output values (e.g., ('macd', 'signal', 'histogram'))."""

    @abstractmethod
    def _calculate_single(self, data: IndicatorData, index: int) -> tuple[Decimal, ...]:
        """Calculate all output values for a single index."""

    def _calculate(self, data: IndicatorData) -> list[IndicatorResult[tuple[Decimal, ...]]]:
        results = []
        start = self.required_data_points - 1
        for i in range(start, len(data)):
            values = self._calculate_single(data, i)
            results.append(
                IndicatorResult(
                    name=self.name,
                    indicator_type=self.indicator_type,
                    timestamp=data[i].timestamp,
                    value=values,
                    parameters=self.config.parameters,
                    metadata={"output_names": self.output_names},
                )
            )
        return results


def validate_ohlcv_sequence(data: IndicatorData, min_length: int = 1) -> None:
    """Validate a sequence of OHLCV data."""
    if len(data) < min_length:
        raise InsufficientDataError(
            f"Requires at least {min_length} data points, got {len(data)}",
            required_length=min_length,
            provided_length=len(data),
        )
    for i, ohlcv in enumerate(data):
        if not isinstance(ohlcv, OHLCV):
            raise InvalidDataError(f"Element at index {i} is not OHLCV", invalid_indices=[i])


def validate_positive_int(value: Any, name: str, min_value: int = 1) -> int:
    """Validate a positive integer parameter."""
    try:
        ivalue = int(value)
    except (ValueError, TypeError) as e:
        raise InvalidParameterError(f"{name} must be an integer", parameter_name=name, parameter_value=value) from e
    if ivalue < min_value:
        raise InvalidParameterError(
            f"{name} must be >= {min_value}", parameter_name=name, parameter_value=ivalue, valid_range=(min_value, None)
        )
    return ivalue


def validate_positive_decimal(value: Any, name: str, min_value: Decimal = Decimal("0")) -> Decimal:
    """Validate a positive decimal parameter."""
    try:
        dvalue = Decimal(str(value))
    except (ValueError, TypeError) as e:
        raise InvalidParameterError(f"{name} must be a valid decimal", parameter_name=name, parameter_value=value) from e
    if dvalue < min_value:
        raise InvalidParameterError(
            f"{name} must be >= {min_value}", parameter_name=name, parameter_value=dvalue, valid_range=(min_value, None)
        )
    return dvalue


def validate_period(period: Any, name: str, max_period: int | None = None) -> int:
    """Validate a period parameter."""
    period_int = validate_positive_int(period, name)
    if max_period and period_int > max_period:
        raise InvalidParameterError(
            f"{name} must be <= {max_period}", parameter_name=name, parameter_value=period_int, valid_range=(1, max_period)
        )
    return period_int


def validate_smoothing_factor(alpha: Any, name: str = "alpha") -> Decimal:
    """Validate a smoothing factor (0 < alpha <= 1)."""
    alpha_decimal = validate_positive_decimal(alpha, name, Decimal("0"))
    if alpha_decimal > Decimal("1"):
        raise InvalidParameterError(
            f"{name} must be <= 1", parameter_name=name, parameter_value=alpha_decimal, valid_range=(Decimal("0"), Decimal("1"))
        )
    return alpha_decimal