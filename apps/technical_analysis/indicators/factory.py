"""Factory for creating indicator instances."""

from __future__ import annotations

from typing import Any

from apps.technical_analysis.indicators.base import BaseIndicator, IndicatorConfig, IndicatorType
from apps.technical_analysis.indicators.exceptions import IndicatorConfigurationError, IndicatorNotFoundError
from apps.technical_analysis.indicators.registry import IndicatorRegistry, get_registry


class IndicatorFactory:
    """Factory for creating indicator instances with validation."""

    def __init__(self, registry: IndicatorRegistry | None = None) -> None:
        self._registry = registry or get_registry()
        self._custom_validators: dict[str, list[callable]] = {}

    def create(
        self,
        name: str,
        parameters: dict[str, Any] | None = None,
        indicator_type: IndicatorType | None = None,
        required_data_points: int | None = None,
    ) -> BaseIndicator[Any]:
        """Create an indicator instance with given parameters."""
        params = parameters or {}
        reg_name = name.lower()

        defaults = self._registry.get_defaults(reg_name)
        merged_params = {**defaults, **params}

        if indicator_type is None:
            indicator_type = IndicatorType(params.get("type", "custom"))

        if required_data_points is None:
            required_data_points = params.get("required_data_points", 1)

        config = IndicatorConfig(
            name=reg_name,
            indicator_type=indicator_type,
            parameters=merged_params,
            required_data_points=required_data_points,
        )

        self._validate(name, config)
        return self._registry.create(reg_name, config)

    def create_from_config(self, config: IndicatorConfig) -> BaseIndicator[Any]:
        """Create an indicator from a pre-built config."""
        self._validate(config.name, config)
        return self._registry.create(config.name, config)

    def register_validator(self, name: str, validator: callable) -> None:
        """Register a custom validator for an indicator."""
        reg_name = name.lower()
        if reg_name not in self._custom_validators:
            self._custom_validators[reg_name] = []
        self._custom_validators[reg_name].append(validator)

    def _validate(self, name: str, config: IndicatorConfig) -> None:
        """Validate configuration using registered validators."""
        validators = self._registry.get_validators(name)
        for validator in validators:
            try:
                validator(config.parameters)
            except Exception as e:
                raise IndicatorConfigurationError(
                    f"Validation failed for {name}: {e}",
                    indicator_name=name,
                ) from e

        custom = self._custom_validators.get(name.lower(), [])
        for validator in custom:
            try:
                validator(config.parameters)
            except Exception as e:
                raise IndicatorConfigurationError(
                    f"Custom validation failed for {name}: {e}",
                    indicator_name=name,
                ) from e

    def get_defaults(self, name: str) -> dict[str, Any]:
        """Get default parameters for an indicator."""
        return self._registry.get_defaults(name.lower())

    def list_available(self) -> list[str]:
        """List all available indicators."""
        return self._registry.get_names()

    def list_by_type(self, indicator_type: IndicatorType) -> list[str]:
        """List indicators by type."""
        return sorted(self._registry.get_by_type(indicator_type).keys())


def create_indicator(
    name: str,
    parameters: dict[str, Any] | None = None,
    **kwargs: Any,
) -> BaseIndicator[Any]:
    """Convenience function to create an indicator."""
    factory = IndicatorFactory()
    return factory.create(name, parameters, **kwargs)


def create_indicators(configs: list[dict[str, Any]]) -> list[BaseIndicator[Any]]:
    """Create multiple indicators from config list."""
    factory = IndicatorFactory()
    return [factory.create(**c) for c in configs]


def get_indicator_defaults(name: str) -> dict[str, Any]:
    """Get default parameters for an indicator."""
    factory = IndicatorFactory()
    return factory.get_defaults(name)