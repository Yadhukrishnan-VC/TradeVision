"""
Technical Analysis Indicators Package.

Pure Python implementation of technical indicators for financial markets.
No Django dependencies. Pure calculations only.
"""

from apps.technical_analysis.indicators.base import (
    BaseIndicator,
    IndicatorConfig,
    IndicatorData,
    IndicatorResult,
    IndicatorType,
    MultiValueIndicator,
    OHLCV,
    SingleValueIndicator,
    Timeframe,
    validate_ohlcv_sequence,
    validate_period,
    validate_positive_decimal,
    validate_positive_int,
    validate_smoothing_factor,
)
from apps.technical_analysis.indicators.exceptions import (
    CalculationError,
    ConfigurationError,
    IndicatorError,
    IndicatorNotFoundError,
    InsufficientDataError,
    InvalidConfigurationError,
    InvalidDataError,
    InvalidParameterError,
)
from apps.technical_analysis.indicators.factory import (
    IndicatorBuilder,
    IndicatorFactory,
    create_indicator,
    create_indicators,
    get_indicator_defaults,
)
from apps.technical_analysis.indicators.registry import (
    IndicatorRegistry,
    get_registry,
    list_indicators,
    list_indicators_by_type,
    register_indicator,
)

__version__ = "1.0.0"

__all__ = [
    "BaseIndicator",
    "IndicatorConfig",
    "IndicatorData",
    "IndicatorResult",
    "IndicatorType",
    "MultiValueIndicator",
    "OHLCV",
    "SingleValueIndicator",
    "Timeframe",
    "validate_ohlcv_sequence",
    "validate_period",
    "validate_positive_decimal",
    "validate_positive_int",
    "validate_smoothing_factor",
    "CalculationError",
    "ConfigurationError",
    "IndicatorError",
    "IndicatorNotFoundError",
    "InsufficientDataError",
    "InvalidConfigurationError",
    "InvalidDataError",
    "InvalidParameterError",
    "IndicatorBuilder",
    "IndicatorFactory",
    "create_indicator",
    "create_indicators",
    "get_indicator_defaults",
    "IndicatorRegistry",
    "get_registry",
    "list_indicators",
    "list_indicators_by_type",
    "register_indicator",
]

from apps.technical_analysis.indicators import trend, momentum, volatility, volume

__all__ += ["trend", "momentum", "volatility", "volume"]