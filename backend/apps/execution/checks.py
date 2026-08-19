from __future__ import annotations

from django.conf import settings
from django.core import checks

_ALLOWED_ENVIRONMENTS = frozenset({"sandbox", "live"})


@checks.register("execution")
def broker_environment_check(app_configs=None, **kwargs) -> list[checks.Error]:
    """Validate the broker execution environment at Django startup.

    LIVE-BROKER-EXECUTION-1 (Phase 1 of 3) is sandbox-only. A configured
    ``BROKER_ENVIRONMENT=live`` must fail startup — not fall back silently —
    until the Phase 2 explicit unlock exists (ADR-030). ``live`` is therefore
    entirely unreachable in this batch: the Phase-2 unlock mechanism does not
    exist yet, so the check always fails on ``live``.
    """
    errors: list[checks.Error] = []
    env = getattr(settings, "BROKER_ENVIRONMENT", "sandbox").lower()

    if env not in _ALLOWED_ENVIRONMENTS:
        errors.append(
            checks.Error(
                f"BROKER_ENVIRONMENT must be one of "
                f"{sorted(_ALLOWED_ENVIRONMENTS)}; got {env!r}.",
                hint="Set BROKER_ENVIRONMENT=sandbox (Phase 1 only).",
                id="execution.E002",
            )
        )

    if env == "live":
        errors.append(
            checks.Error(
                "BROKER_ENVIRONMENT=live is unreachable in this batch: the "
                "Phase 2 explicit live unlock (ADR-030) is not implemented, "
                "so the app must never start in live mode.",
                hint="Keep BROKER_ENVIRONMENT=sandbox until the ADR-030 "
                "Phase 2 gate (owner sign-off, hard risk caps, verified "
                "kill switch, incident/rollback procedure) is satisfied.",
                id="execution.E001",
            )
        )

    if env == "live" and not getattr(settings, "ALGO_REGISTRATION_ID", "").strip():
        errors.append(
            checks.Error(
                "BROKER_ENVIRONMENT=live requires ALGO_REGISTRATION_ID to be "
                "set: algorithmic live trading must be tied to an explicit, "
                "recorded SEBI algotrading registration decision.",
                hint="Set ALGO_REGISTRATION_ID to the operator's registered "
                "algo-trading identifier before any live execution is "
                "attempted.",
                id="execution.E003",
            )
        )

    return errors
