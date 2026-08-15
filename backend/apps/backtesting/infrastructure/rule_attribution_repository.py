"""RuleExecution lookups that back per-rule backtest trade attribution (Batch M4.5).

The join key between the execution side and the rule engine is the shared
correlation id: ``Order.correlation_id`` equals ``RuleExecution.analysis_event_id``
(the id of the analysis event, one per historical bar, that triggered the
firing). This repository is read-only and deliberately small; the heavy
grouping logic lives in the pure ``apps.backtesting.domain.attribution``
module.
"""

from __future__ import annotations

import uuid

from apps.rule_engine.infrastructure.models import RuleExecution


class RuleAttributionRepository:
    """Source of the rule responsible for each bar's orders in a backtest."""

    def get_rule_executions(
        self, correlation_ids: set[uuid.UUID]
    ) -> list[RuleExecution]:
        """Fetch ``RuleExecution`` rows for the given order correlation ids.

        Rows come back newest-first (the ``BaseModel`` default) so the
        deterministic first-row-wins tie-break in
        ``build_correlation_to_rule_map`` matches ``_resolve_regimes``.
        """
        if not correlation_ids:
            return []
        return list(
            RuleExecution.objects.filter(
                analysis_event_id__in=correlation_ids
            ).only("analysis_event_id", "rule_id")
        )
