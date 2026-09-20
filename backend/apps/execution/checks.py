from __future__ import annotations

from django.conf import settings
from django.core import checks

_SANDBOX_ENVIRONMENT = "sandbox"
_LIVE_ENVIRONMENT = "live"


@checks.register("execution")
def broker_environment_check(app_configs=None, **kwargs) -> list[checks.Error]:
    """Validate the broker execution environment at Django startup.

    LIVE-BROKER-EXECUTION-1 (Phase 1 of 3):

    - ``BROKER_ENVIRONMENT=sandbox``: Always allowed — paper/trading-sandbox mode.
    - ``BROKER_ENVIRONMENT=live``: Allowed only when ``ALGO_REGISTRATION_ID`` is
      set — this is the Phase-2 explicit unlock (ADR-030). The ID must be the
      operator's registered SEBI algotrading identifier.

    If ``ALGO_REGISTRATION_ID`` is not set and the environment is ``live``, the
    check fails with id ``execution.E003``, prompting the operator to set the
    registration ID before any live execution is attempted.

    If the environment is neither ``sandbox`` nor ``live``, the check fails with
    id ``execution.E002``.
    """
    errors: list[checks.Error] = []
    env = getattr(settings, "BROKER_ENVIRONMENT", _SANDBOX_ENVIRONMENT).lower()

    if env not in (_SANDBOX_ENVIRONMENT, _LIVE_ENVIRONMENT):
        errors.append(
            checks.Error(
                f"BROKER_ENVIRONMENT must be one of "
                f"{[_SANDBOX_ENVIRONMENT, _LIVE_ENVIRONMENT]}; got {env!r}.",
                hint=f"Set BROKER_ENVIRONMENT={_SANDBOX_ENVIRONMENT} (Phase 1) "
                f"or {_LIVE_ENVIRONMENT} (Phase 2 ADR-030).",
                id="execution.E002",
            )
        )

    if env == _LIVE_ENVIRONMENT:
        # Phase-2 explicit unlock: live mode requires a recorded SEBI
        # algo-trading registration identifier.
        algo_registration_id = getattr(
            settings, "ALGO_REGISTRATION_ID", ""
        ).strip()
        if not algo_registration_id:
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
        # If ALGO_REGISTRATION_ID is set, the Phase-2 gate is considered passed.
        # The operator has formally registered their algo-trading system with SEBI.

    return errors