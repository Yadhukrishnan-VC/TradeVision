"""
TradeVision AI — PromptManager service.

Loads, versions, and renders Jinja2 prompt templates. Templates are stored
in ``core/ai/prompts/`` and loaded at import time.

Usage::

    from apps.ai_engine.prompt_manager.service import PromptManager

    pm = PromptManager()
    template = pm.get_template("price_movement")
    prompt = pm.render(template, signal_context=ctx, portfolio_state=ps)
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)

TEMPLATE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent / "core" / "ai" / "prompts"
"""Path to the Jinja2 template directory."""

TEMPLATE_NAMES: dict[str, str] = {
    "price_movement": "price_movement.j2",
    "volume_spike": "volume_spike.j2",
    "breakout": "breakout.j2",
    "breakdown": "price_movement.j2",
    "circuit_breaker": "price_movement.j2",
    "gap_movement": "price_movement.j2",
    "announcement": "announcement.j2",
    "earnings": "earnings.j2",
    "institutional_activity": "institutional_activity.j2",
    "macro_event": "macro_event.j2",
    "multi_event": "multi_event.j2",
}
"""Maps EventType values to template filenames."""


class PromptManager:
    """Manages prompt template lifecycle: loading, versioning, rendering."""

    def __init__(self) -> None:
        self._env: Environment = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=False,
        )
        self._templates: dict[str, Template] = {}
        self._versions: dict[str, str] = {}
        self._load_templates()

    def _load_templates(self) -> None:
        """Load all templates and compute their versions."""
        for event_type, filename in TEMPLATE_NAMES.items():
            try:
                template = self._env.get_template(filename)
                source = self._env.loader.get_source(self._env, filename)[0]
                version = self._compute_version(source)
                self._templates[event_type] = template
                self._versions[event_type] = version
                logger.info(
                    "prompt_template_loaded",
                    extra={
                        "event_type": event_type,
                        "filename": filename,
                        "version": version,
                    },
                )
            except Exception as exc:
                logger.error(
                    "prompt_template_load_failed",
                    extra={"event_type": event_type, "error": str(exc)},
                )

    def _compute_version(self, source: str) -> str:
        """Compute template version from content hash or VERSION comment."""
        version_match = re.search(r"VERSION:\s*([\w.]+)", source)
        if version_match:
            return version_match.group(1)
        return hashlib.sha256(source.encode()).hexdigest()[:12]

    def get_template(self, event_type: str) -> Template | None:
        """Return the Jinja2 template for the given event type."""
        return self._templates.get(event_type)

    def render(
        self,
        event_type: str,
        signal_context: dict[str, Any] | None = None,
        portfolio_state: str | None = None,
        risk_state: str | None = None,
        trading_history: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> str:
        """Render a prompt template with the given context.

        Args:
            event_type: The event type key (e.g. ``"price_movement"``).
            signal_context: Dict with keys: pine_output, market_regime,
                multi_timeframe_alignment, news_headlines, sector_context,
                event_* fields.
            portfolio_state: Serialized portfolio state string.
            risk_state: Serialized risk state string.
            trading_history: List of recent trader memory records.
            **kwargs: Additional template variables.

        Returns:
            Rendered prompt string.

        Raises:
            ValueError: If the template for ``event_type`` is not found.
        """
        template = self.get_template(event_type)
        if template is None:
            raise ValueError(
                f"No template found for event type '{event_type}'. "
                f"Available types: {sorted(self._templates.keys())}"
            )

        context: dict[str, Any] = dict(kwargs)
        if signal_context:
            context["pine_output"] = signal_context.get("pine_output", "")
            context["market_regime"] = signal_context.get("market_regime", "UNKNOWN")
            context["multi_timeframe_alignment"] = signal_context.get(
                "multi_timeframe_alignment", "NEUTRAL"
            )
            context["news_headlines"] = signal_context.get("news_headlines", [])
            context["sector_context"] = signal_context.get("sector_context", "")
            context["event"] = signal_context.get("event", {})

        context["portfolio_state"] = portfolio_state
        context["risk_state"] = risk_state
        context["trading_history"] = trading_history or []

        return template.render(**context)

    def get_version(self, event_type: str) -> str:
        """Return the version string for the given template."""
        return self._versions.get(event_type, "unknown")

    def list_versions(self) -> dict[str, str]:
        """Return a dict of all template versions keyed by event type."""
        return dict(self._versions)
