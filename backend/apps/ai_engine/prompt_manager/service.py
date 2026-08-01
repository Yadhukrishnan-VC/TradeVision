from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone
from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)

TEMPLATE_DIR: Path = Path(__file__).resolve().parent.parent.parent.parent / "core" / "ai" / "prompts"

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


class PromptManager:
    def __init__(self) -> None:
        self._env: Environment = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=False,
        )
        self._templates: dict[str, Template] = {}
        self._versions: dict[str, str] = {}
        self._load_templates()

    def _load_templates(self) -> None:
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
                self._ensure_persisted_version(event_type, source, version)
            except Exception as exc:
                logger.error(
                    "prompt_template_load_failed",
                    extra={"event_type": event_type, "error": str(exc)},
                )

    def _compute_version(self, source: str) -> str:
        version_match = re.search(r"VERSION:\s*([\w.]+)", source)
        if version_match:
            return version_match.group(1)
        return hashlib.sha256(source.encode()).hexdigest()[:12]

    def _ensure_persisted_version(self, event_type: str, source: str, version: str) -> None:
        if not getattr(settings, "PROMPT_VERSIONING_PERSISTENCE_ENABLED", False):
            return
        from apps.ai_engine.models import PromptVersion

        PromptVersion.objects.get_or_create(
            event_type=event_type,
            version_hash=version,
            defaults={
                "source_snapshot": source,
                "is_active": not PromptVersion.objects.filter(
                    event_type=event_type, is_active=True
                ).exists(),
            },
        )
        logger.debug(
            "prompt_version_persisted",
            extra={"event_type": event_type, "version": version},
        )

    def _get_active_version(self, event_type: str) -> str | None:
        if not getattr(settings, "PROMPT_VERSIONING_PERSISTENCE_ENABLED", False):
            return None
        from apps.ai_engine.models import PromptVersion

        try:
            active = PromptVersion.objects.filter(
                event_type=event_type, is_active=True
            ).latest("activated_at")
            return active.version_hash
        except PromptVersion.DoesNotExist:
            return None

    def get_template(self, event_type: str) -> Template | None:
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
        active_version = self._get_active_version(event_type)
        if active_version and active_version in self._versions.values():
            pass

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
            context["bullishness_score"] = signal_context.get("bullishness_score", 0.0)
            context["bearishness_score"] = signal_context.get("bearishness_score", 0.0)
            context["volatility_score"] = signal_context.get("volatility_score", 0.0)
            context["trend_score"] = signal_context.get("trend_score", 0.0)
            context["liquidity_score"] = signal_context.get("liquidity_score", 0.0)
            context["momentum_score"] = signal_context.get("momentum_score", 0.0)
            context["overall_context_confidence"] = signal_context.get(
                "overall_context_confidence", 0.0
            )
            context["pattern_alignment_note"] = signal_context.get(
                "pattern_alignment_note", "PATTERN_ENGINE_NOT_AVAILABLE"
            )

        context["portfolio_state"] = portfolio_state
        context["risk_state"] = risk_state
        context["trading_history"] = trading_history or []

        return template.render(**context)

    def get_version(self, event_type: str) -> str:
        active_version = self._get_active_version(event_type)
        if active_version:
            return active_version
        return self._versions.get(event_type, "unknown")

    def list_versions(self) -> dict[str, str]:
        return dict(self._versions)

    def activate_version(self, event_type: str, version: str) -> None:
        from apps.ai_engine.models import PromptVersion

        PromptVersion.objects.filter(event_type=event_type, is_active=True).update(
            is_active=False
        )

        updated = PromptVersion.objects.filter(
            event_type=event_type, version_hash=version
        ).update(is_active=True, activated_at=timezone.now())

        if updated == 0:
            raise ValueError(
                f"No PromptVersion found for event_type='{event_type}', "
                f"version='{version}'"
            )

        logger.info(
            "prompt_version_activated",
            extra={"event_type": event_type, "version": version},
        )

    def rollback(self, event_type: str) -> str:
        from apps.ai_engine.models import PromptVersion

        versions = list(
            PromptVersion.objects.filter(event_type=event_type).order_by("-activated_at")
        )

        if len(versions) < 2:
            raise ValueError(
                f"Cannot rollback event_type='{event_type}': "
                f"need at least 2 versions, found {len(versions)}"
            )

        current = versions[0]
        previous = versions[1]

        PromptVersion.objects.filter(event_type=event_type, is_active=True).update(
            is_active=False
        )
        PromptVersion.objects.filter(
            event_type=event_type, id=previous.id
        ).update(is_active=True, activated_at=timezone.now())

        logger.info(
            "prompt_version_rollback",
            extra={
                "event_type": event_type,
                "from_version": current.version_hash,
                "to_version": previous.version_hash,
            },
        )

        return previous.version_hash

    def get_history(self, event_type: str) -> list[dict[str, Any]]:
        from apps.ai_engine.models import PromptVersion

        qs = PromptVersion.objects.filter(event_type=event_type).order_by(
            "-activated_at", "-created_at"
        )
        return [
            {
                "id": str(pv.id),
                "event_type": pv.event_type,
                "version_hash": pv.version_hash,
                "is_active": pv.is_active,
                "activated_at": pv.activated_at.isoformat() if pv.activated_at else None,
                "created_at": pv.created_at.isoformat() if pv.created_at else None,
            }
            for pv in qs
        ]
