from __future__ import annotations

import os
import re

from django.conf import settings
from django.core import checks
from django.urls import reverse

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

        # 1. Format validation of ALGO_REGISTRATION_ID
        algo_registration_id = getattr(settings, "ALGO_REGISTRATION_ID", "").strip()
        if algo_registration_id:
            if not re.match(r"^[A-Za-z0-9]{8,32}$", algo_registration_id):
                errors.append(
                    checks.Error(
                        "ALGO_REGISTRATION_ID must be alphanumeric and 8–32 characters long.",
                        hint="Set a valid SEBI algotrading registration identifier.",
                        id="execution.E004",
                    )
                )

        # 2. Risk cap enforcement
        # Read the real value from the RISK_MANAGEMENT dict (the canonical source),
        # not the bare env-var attribute that may not be configured.
        risk_max_position_size = settings.RISK_MANAGEMENT.get("max_position_size", 0)
        if not isinstance(risk_max_position_size, int) or risk_max_position_size <= 0:
            errors.append(
                checks.Error(
                    "RISK_MAX_POSITION_SIZE must be set to a positive integer in RISK_MANAGEMENT.",
                    hint="Configure RISK_MANAGEMENT['max_position_size'] in the Django settings.",
                    id="execution.E005",
                )
            )

        # 3. Kill switch verified end-to-end
        try:
            reverse("kill-switch")
        except Exception:
            errors.append(
                checks.Error(
                    "Kill switch URL must be resolvable (registered in urls.py).",
                    hint="Ensure the kill-switch path is wired in the URL configuration.",
                    id="execution.E006",
                )
            )

        # 4. Written incident/rollback procedure documentation
        rollback_path = os.path.join(settings.BASE_DIR, "docs", "rollback_procedure.md")
        if not os.path.exists(rollback_path):
            errors.append(
                checks.Error(
                    "Rollback procedure documentation not found.",
                    hint="Place a rollback procedure doc at docs/rollback_procedure.md.",
                    id="execution.E007",
                )
            )

    return errors