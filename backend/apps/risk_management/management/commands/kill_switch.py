"""
Management command: kill_switch

Out-of-band trade-safety halt (ADR-030 §5.3). Activates/deactivates the
persistent kill switch without going through the API surface, so trading can
be halted even when the API is unreachable or itself misbehaving. The state
row written here is the same one the API path writes
(``KillSwitchService``), and every toggle publishes an auditable
``risk_management.KillSwitchActivated`` / ``KillSwitchDeactivated`` event.

The risk check chain reads this state on every evaluation and rejects with
``KILL_SWITCH_ACTIVE`` while any covering scope is active — so activating a
scope here halts the RuleFired -> RiskDecision -> Order pipeline immediately.

Usage::

    python manage.py kill_switch --status
    python manage.py kill_switch --activate --scope GLOBAL --reason "adapter misbehaving"
    python manage.py kill_switch --activate --scope SYMBOL --symbol RELIANCE --reason "bad ticks"
    python manage.py kill_switch --deactivate --scope GLOBAL --reason "incident closed"
"""

from __future__ import annotations

from typing import Any

from apps.risk_management.application.kill_switch_service import KillSwitchService
from apps.risk_management.domain.value_objects import KillSwitchScope
from apps.risk_management.infrastructure.models import KillSwitchState
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Out-of-band trade-halt control (ADR-030 §5.3): activate/deactivate "
        "the persistent kill switch outside the API surface."
    )

    def add_arguments(self, parser) -> None:
        actions = parser.add_mutually_exclusive_group(required=True)
        actions.add_argument(
            "--activate",
            dest="activate",
            action="store_true",
            help="Activate the kill switch for the given scope.",
        )
        actions.add_argument(
            "--deactivate",
            dest="deactivate",
            action="store_true",
            help="Deactivate the kill switch for the given scope.",
        )
        actions.add_argument(
            "--status",
            dest="status",
            action="store_true",
            help="Show active kill-switch scopes and exit.",
        )
        parser.add_argument(
            "--scope",
            dest="scope",
            default=None,
            choices=[s.value for s in KillSwitchScope],
            help="Scope to toggle (GLOBAL blocks every symbol; required for activate/deactivate).",
        )
        parser.add_argument(
            "--symbol",
            dest="symbol",
            default=None,
            help="Symbol for scope=SYMBOL toggles.",
        )
        parser.add_argument(
            "--reason",
            dest="reason",
            default="manual halt via manage.py kill_switch",
            help="Audit reason recorded with the toggle.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        service = KillSwitchService()
        scope: str | None = options["scope"]
        symbol: str | None = options["symbol"]

        if options["status"]:
            self._print_status()
            return

        if not scope:
            raise CommandError("--scope is required for --activate/--deactivate.")
        if symbol and scope != KillSwitchScope.SYMBOL.value:
            raise CommandError(
                f"--symbol is only valid with --scope {KillSwitchScope.SYMBOL.value}."
            )
        if scope == KillSwitchScope.SYMBOL.value and not symbol:
            raise CommandError("--scope SYMBOL requires --symbol.")

        if options["activate"]:
            state = service.activate(
                scope=scope, symbol=symbol, reason=options["reason"], actor="manage.py"
            )
            self.stdout.write(
                self.style.ERROR(
                    f"KILL SWITCH ACTIVE scope={state.scope} symbol={state.symbol or '*'} "
                    f"reason={state.reason!r} — all covered order flow is now rejected."
                )
            )
            return

        deactivated = service.deactivate(
            scope=scope, symbol=symbol, reason=options["reason"], actor="manage.py"
        )
        if deactivated:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Kill switch deactivated scope={scope} symbol={symbol or '*'}."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Kill switch was not active scope={scope} symbol={symbol or '*'}."
                )
            )

    def _print_status(self) -> None:
        rows = KillSwitchState.objects.filter(is_active=True).order_by(
            "scope", "symbol"
        )
        if not rows:
            self.stdout.write("No active kill-switch scopes.")
            return
        for row in rows:
            self.stdout.write(
                f"ACTIVE scope={row.scope} symbol={row.symbol or '*'} "
                f"since={row.activated_at.isoformat()} actor={row.actor} reason={row.reason!r}"
            )
