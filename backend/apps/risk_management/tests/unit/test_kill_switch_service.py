from __future__ import annotations

import pytest

from apps.risk_management.application.kill_switch_service import KillSwitchService
from apps.risk_management.infrastructure.cache import KillSwitchCache


class ExplodingCache(KillSwitchCache):
    """Cache whose reads always raise — must fail closed."""

    def get(self, scope: str, symbol: str | None = None) -> bool | None:
        raise RuntimeError("cache down")

    def set(self, scope: str, symbol: str | None, active: bool) -> None:
        raise RuntimeError("cache down")


class ExplodingRepository:
    def has_active(self, scope: str, symbol: str | None) -> bool:
        raise RuntimeError("db down")


@pytest.mark.django_db
class TestKillSwitchService:
    def test_is_active_default_false(self) -> None:
        service = KillSwitchService()
        assert service.is_active("GLOBAL") is False

    def test_activate_then_is_active_true(self) -> None:
        service = KillSwitchService()
        service.activate(scope="GLOBAL", reason="test")
        assert service.is_active("GLOBAL") is True

    def test_is_trade_blocked_false_when_nothing_active(self) -> None:
        assert KillSwitchService().is_trade_blocked("RELIANCE") is False

    def test_global_kill_switch_blocks_symbol(self) -> None:
        service = KillSwitchService()
        service.activate(scope="GLOBAL", reason="halt")
        assert service.is_trade_blocked("RELIANCE") is True

    def test_symbol_kill_switch_blocks_only_that_symbol(self) -> None:
        service = KillSwitchService()
        service.activate(scope="SYMBOL", symbol="RELIANCE", reason="halt")
        assert service.is_trade_blocked("RELIANCE") is True
        assert service.is_trade_blocked("TCS") is False

    def test_deactivate_restores_flow(self) -> None:
        service = KillSwitchService()
        service.activate(scope="SYMBOL", symbol="RELIANCE", reason="halt")
        assert service.is_trade_blocked("RELIANCE") is True
        service.deactivate(scope="SYMBOL", symbol="RELIANCE", reason="resume")
        assert service.is_trade_blocked("RELIANCE") is False

    def test_fail_closed_on_cache_error(self) -> None:
        service = KillSwitchService(cache=ExplodingCache())
        # Cache error => falls back to DB (nothing active) => False.
        assert service.is_active("GLOBAL") is False

    def test_fail_closed_on_db_error(self) -> None:
        service = KillSwitchService(
            repository=ExplodingRepository(),  # type: ignore[arg-type]
            cache=KillSwitchCache(),
        )
        assert service.is_active("GLOBAL") is True

    def test_partial_unique_active_scope_symbol(self) -> None:
        service = KillSwitchService()
        service.activate(scope="SYMBOL", symbol="RELIANCE", reason="first")
        service.activate(scope="SYMBOL", symbol="RELIANCE", reason="second")
        from apps.risk_management.infrastructure.models import KillSwitchState

        active = KillSwitchState.objects.filter(
            scope="SYMBOL", symbol="RELIANCE", is_active=True
        )
        assert active.count() == 1
        assert active.get().reason == "second"
