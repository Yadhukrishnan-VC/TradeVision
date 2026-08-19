from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from django.utils import timezone as dj_timezone

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.risk_management.domain.events import (
    KillSwitchActivated,
    KillSwitchDeactivated,
)
from apps.risk_management.domain.value_objects import KillSwitchScope
from apps.risk_management.infrastructure.cache import KillSwitchCache
from apps.risk_management.infrastructure.models import KillSwitchState
from apps.risk_management.infrastructure.repositories import KillSwitchStateRepository
from core.services import BaseService

logger = logging.getLogger(__name__)


class KillSwitchService(BaseService):
    """Read-through, fail-closed kill-switch state management.

    ``is_trade_blocked(symbol)`` answers "should this trade be blocked?" by
    checking SYMBOL → ACCOUNT → GLOBAL (most-specific wins). Every lookup
    error — cache or database — resolves to *blocked* (fail-closed).

    Toggles persist a ``KillSwitchState`` row and publish a domain event that
    the audit-log ``*`` subscriber records for free.
    """

    def __init__(
        self,
        repository: KillSwitchStateRepository | None = None,
        cache: KillSwitchCache | None = None,
    ) -> None:
        super().__init__()
        self._repository = repository or KillSwitchStateRepository()
        self._cache = cache or KillSwitchCache()

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    def is_trade_blocked(self, symbol: str) -> bool:
        """Return whether the symbol is blocked by any kill-switch scope.

        Fail-closed: on any lookup error the trade is considered blocked.
        """
        for scope in (
            KillSwitchScope.SYMBOL,
            KillSwitchScope.ACCOUNT,
            KillSwitchScope.GLOBAL,
        ):
            if self._is_active(scope.value, symbol if scope is KillSwitchScope.SYMBOL else None):
                return True
        return False

    def is_active(self, scope: str, symbol: str | None = None) -> bool:
        """Return the active-state of a single scope (fail-closed)."""
        return self._is_active(scope, symbol)

    def _is_active(self, scope: str, symbol: str | None) -> bool:
        try:
            cached = self._cache.get(scope, symbol)
            if cached is not None:
                return cached
        except Exception:
            logger.exception(
                "kill_switch_cache_read_error",
                extra={"scope": scope, "symbol": symbol},
            )
        try:
            active = self._repository.has_active(scope, symbol)
        except Exception:
            logger.exception(
                "kill_switch_db_read_error",
                extra={"scope": scope, "symbol": symbol},
            )
            return True  # fail-closed
        try:
            self._cache.set(scope, symbol, active)
        except Exception:
            logger.exception(
                "kill_switch_cache_write_error",
                extra={"scope": scope, "symbol": symbol},
            )
        return active

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def activate(
        self,
        scope: str,
        symbol: str | None = None,
        reason: str = "",
        actor: str = "system",
        correlation_id: uuid.UUID | None = None,
    ) -> KillSwitchState:
        """Activate a kill-switch scope and publish ``KillSwitchActivated``."""
        self._validate_scope_symbol(scope, symbol)
        scope_enum = KillSwitchScope(scope)
        self._repository.deactivate_all_for_scope_symbol(scope, symbol)

        state = KillSwitchState(
            scope=scope,
            symbol=symbol,
            is_active=True,
            activated_at=dj_timezone.now(),
            actor=actor,
            reason=reason,
        )
        state.full_clean()
        state.save()

        self._cache.set(scope, symbol, True)
        self._publish_toggle_event(
            KillSwitchActivated(
                scope=scope_enum,
                symbol=symbol,
                actor=actor,
                reason=reason,
            ),
            correlation_id=correlation_id,
        )
        return state

    def deactivate(
        self,
        scope: str,
        symbol: str | None = None,
        reason: str = "",
        actor: str = "system",
        correlation_id: uuid.UUID | None = None,
    ) -> bool:
        """Deactivate a kill-switch scope and publish ``KillSwitchDeactivated``."""
        self._validate_scope_symbol(scope, symbol)
        scope_enum = KillSwitchScope(scope)
        updated = self._repository.deactivate_all_for_scope_symbol(scope, symbol)

        self._cache.set(scope, symbol, False)
        if updated:
            self._publish_toggle_event(
                KillSwitchDeactivated(
                    scope=scope_enum,
                    symbol=symbol,
                    actor=actor,
                    reason=reason,
                ),
                correlation_id=correlation_id,
            )
        return updated > 0

    # ------------------------------------------------------------------
    # Automatic drawdown breaker (Risk Sophistication batch)
    # ------------------------------------------------------------------

    def evaluate_drawdown_limits(
        self,
        *,
        daily_loss: Decimal,
        weekly_loss: Decimal,
        capital: Decimal,
        max_daily_loss_pct: Decimal | None = None,
        max_weekly_loss_pct: Decimal | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> KillSwitchState | None:
        """Auto-activate the ACCOUNT kill switch on a realized drawdown breach.

        Compares ``daily_loss``/``weekly_loss`` (non-negative magnitudes) as a
        share of ``capital`` against the configured percentage thresholds and,
        when breached, activates the ACCOUNT scope with an audit reason that
        captures the values at trip time. Idempotent: when the ACCOUNT scope is
        already active the existing row is returned and no new event is
        published, so a repeating beat never spams the audit log.

        Returns ``None`` when no threshold is breached (or when ``capital`` is
        unusable — the breaker cannot trip on a non-positive capital base).
        """
        if capital is None or capital <= 0:
            logger.warning(
                "drawdown_breaker_skipped_no_capital",
                extra={"capital": str(capital)},
            )
            return None

        existing = self._active_account_state()
        if existing is not None:
            return existing

        daily_pct = daily_loss / capital
        weekly_pct = weekly_loss / capital

        trigger: tuple[str, Decimal, Decimal, Decimal] | None = None
        if (
            max_daily_loss_pct is not None
            and daily_loss > 0
            and daily_pct >= max_daily_loss_pct
        ):
            trigger = ("daily", daily_loss, daily_pct, max_daily_loss_pct)
        elif (
            max_weekly_loss_pct is not None
            and weekly_loss > 0
            and weekly_pct >= max_weekly_loss_pct
        ):
            trigger = ("weekly", weekly_loss, weekly_pct, max_weekly_loss_pct)

        if trigger is None:
            return None

        kind, loss, pct, limit = trigger
        reason = (
            f"auto drawdown trip ({kind}): loss={loss} capital={capital} "
            f"({(pct * 100).quantize(Decimal('0.01'))}%) >= "
            f"max_{kind}_loss_pct={limit}"
        )
        return self.activate(
            scope=KillSwitchScope.ACCOUNT.value,
            reason=reason,
            actor="system",
            correlation_id=correlation_id,
        )

    def _active_account_state(self) -> KillSwitchState | None:
        try:
            return self._repository.get_active(KillSwitchScope.ACCOUNT.value)
        except Exception:
            logger.exception("kill_switch_active_account_read_error")
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_scope_symbol(scope: str, symbol: str | None) -> None:
        if scope not in KillSwitchScope.__members__:
            raise ValueError(f"Unknown kill-switch scope: {scope!r}")
        if symbol is not None and scope != KillSwitchScope.SYMBOL.value:
            raise ValueError(f"symbol must be None for scope {scope!r}")

    def _publish_toggle_event(
        self,
        toggle,
        correlation_id: uuid.UUID | None = None,
    ) -> None:
        event_type = (
            "risk_management.KillSwitchActivated"
            if isinstance(toggle, KillSwitchActivated)
            else "risk_management.KillSwitchDeactivated"
        )
        event = DomainEvent.create(
            event_type=event_type,
            payload=toggle.to_payload(),
            correlation_id=correlation_id or uuid.uuid4(),
        )
        try:
            get_event_bus().publish(event)
        except Exception:
            logger.exception(
                "kill_switch_toggle_publish_failed",
                extra={"event_type": event_type, "scope": toggle.scope.value},
            )
