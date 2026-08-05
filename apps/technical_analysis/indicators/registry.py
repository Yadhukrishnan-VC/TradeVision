"""Registry for indicator registration and discovery."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from apps.technical_analysis.indicators.base import (
    BaseIndicator,
    IndicatorConfig,
    IndicatorType,
)
from apps.technical_analysis.indicators.exceptions import (
    IndicatorAlreadyRegisteredError,
    IndicatorNotFoundError,
)


class IndicatorRegistry:
    """Registry for managing indicator classes."""

    def __init__(self) -> None:
        self._indicators: dict[str, type[BaseIndicator[Any]]] = {}
        self._type_index: dict[IndicatorType, dict[str, type[BaseIndicator[Any]]]] = {}
        self._validators: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self._defaults: dict[str, dict[str, Any]] = {}

    def register(
        self,
        indicator_class: type[BaseIndicator[Any]],
        name: str | None = None,
        indicator_type: IndicatorType | None = None,
        defaults: dict[str, Any] | None = None,
        validators: list[Callable[[dict[str, Any]], None]] | None = None,
    ) -> str:
        """Register an indicator class."""
        reg_name = (name or indicator_class.__name__).lower()

        if reg_name in self._indicators:
            existing = self._indicators[reg_name]
            raise IndicatorAlreadyRegisteredError(
                f"Indicator '{reg_name}' already registered as {existing.__name__}",
                indicator_name=reg_name,
                existing_class=existing,
            )

        self._indicators[reg_name] = indicator_class

        if indicator_type is None:
            if hasattr(indicator_class, "INDICATOR_TYPE"):
                indicator_type = indicator_class.INDICATOR_TYPE
            else:
                indicator_type = IndicatorType.CUSTOM

        if indicator_type not in self._type_index:
            self._type_index[indicator_type] = {}
        self._type_index[indicator_type][reg_name] = indicator_class

        if defaults:
            self._defaults[reg_name] = defaults.copy()

        if validators:
            self._validators[reg_name] = validators.copy()

        return reg_name

    def unregister(self, name: str) -> bool:
        """Unregister an indicator by name."""
        reg_name = name.lower()
        if reg_name not in self._indicators:
            return False

        indicator_class = self._indicators[reg_name]
        indicator_type = getattr(indicator_class, "INDICATOR_TYPE", IndicatorType.CUSTOM)

        del self._indicators[reg_name]

        if indicator_type in self._type_index:
            self._type_index[indicator_type].pop(reg_name, None)
            if not self._type_index[indicator_type]:
                del self._type_index[indicator_type]

        self._defaults.pop(reg_name, None)
        self._validators.pop(reg_name, None)

        return True

    def get(self, name: str) -> type[BaseIndicator[Any]]:
        """Get indicator class by name."""
        reg_name = name.lower()
        if reg_name not in self._indicators:
            available = sorted(self._indicators.keys())
            raise IndicatorNotFoundError(reg_name, available)
        return self._indicators[reg_name]

    def get_all(self) -> dict[str, type[BaseIndicator[Any]]]:
        """Get all registered indicators."""
        return self._indicators.copy()

    def get_by_type(self, indicator_type: IndicatorType) -> dict[str, type[BaseIndicator[Any]]]:
        """Get all indicators of a specific type."""
        return self._type_index.get(indicator_type, {}).copy()

    def get_names(self) -> list[str]:
        """Get all registered indicator names."""
        return sorted(self._indicators.keys())

    def get_types(self) -> list[IndicatorType]:
        """Get all registered indicator types."""
        return list(self._type_index.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an indicator is registered."""
        return name.lower() in self._indicators

    def create(self, name: str, config: IndicatorConfig) -> BaseIndicator[Any]:
        """Create an indicator instance."""
        indicator_class = self.get(name)
        return indicator_class(config)

    def get_defaults(self, name: str) -> dict[str, Any]:
        """Get default parameters for an indicator."""
        return self._defaults.get(name.lower(), {}).copy()

    def get_validators(self, name: str) -> list[Callable[[dict[str, Any]], None]]:
        """Get validators for an indicator."""
        return self._validators.get(name.lower(), []).copy()

    def clear(self) -> None:
        """Clear all registrations."""
        self._indicators.clear()
        self._type_index.clear()
        self._defaults.clear()
        self._validators.clear()


_registry = IndicatorRegistry()


def get_registry() -> IndicatorRegistry:
    """Get the global indicator registry."""
    return _registry


def register_indicator(
    indicator_class: type[BaseIndicator[Any]],
    name: str | None = None,
    indicator_type: IndicatorType | None = None,
    defaults: dict[str, Any] | None = None,
    validators: list[Callable[[dict[str, Any]], None]] | None = None,
) -> str:
    """Register an indicator in the global registry."""
    return _registry.register(indicator_class, name, indicator_type, defaults, validators)


def list_indicators() -> list[str]:
    """List all registered indicator names."""
    return _registry.get_names()


def list_indicators_by_type(indicator_type: IndicatorType) -> list[str]:
    """List indicators of a specific type."""
    return sorted(_registry.get_by_type(indicator_type).keys())


def get_indicator(name: str) -> type[BaseIndicator[Any]]:
    """Get indicator class by name from global registry."""
    return _registry.get(name)


def create_indicator(name: str, config: IndicatorConfig) -> BaseIndicator[Any]:
    """Create indicator instance from global registry."""
    return _registry.create(name, config)