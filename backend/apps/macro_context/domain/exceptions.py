"""MACRO-CONTEXT-1 — domain exceptions."""

from __future__ import annotations


class MacroContextError(Exception):
    """Base class for all macro-context errors."""


class MacroProviderError(MacroContextError):
    """Raised when a macro data provider fails or returns an unexpected response."""


class UnsupportedSeriesError(MacroContextError):
    """Raised when a series outside the vetted SUPPORTED_SERIES set is requested."""
