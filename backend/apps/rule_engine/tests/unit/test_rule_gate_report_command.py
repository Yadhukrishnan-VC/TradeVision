"""rule_gate_report management command tests.

Verifies the ADR-029 §4 gate visibility output: per-rule, per-regime verdicts
(GO / NO_GO / INSUFFICIENT_DATA / NOT_VALIDATED / DISABLED / NO_CONFIG) so it is
visible why a rule is not firing, not just that it is not firing.
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from apps.rule_engine.infrastructure.models import RuleConfig

pytestmark = pytest.mark.django_db


class TestRuleGateReportCommand:
    def test_reports_no_config_for_unconfigured_rules(self) -> None:
        out = StringIO()
        call_command("rule_gate_report", stdout=out)
        text = out.getvalue()
        assert "price_movement_v1" in text
        assert "NO_CONFIG" in text
        assert "rules fireable in at least one reported regime: 0/8" in text

    def test_reports_go_not_validated_and_disabled(self) -> None:
        RuleConfig.objects.create(
            rule_id="price_movement_v1",
            enabled=True,
            validated_regimes={"BULLISH": {"status": "GO"}},
        )
        RuleConfig.objects.create(
            rule_id="volume_spike_v1",
            enabled=True,
            validated_regimes={},
        )
        RuleConfig.objects.create(
            rule_id="short_sell_v1",
            enabled=False,
            validated_regimes={"BULLISH": {"status": "GO"}},
        )

        out = StringIO()
        call_command("rule_gate_report", regime="BULLISH", stdout=out)
        text = out.getvalue()

        row_pm = next(
            line for line in text.splitlines() if line.startswith("price_movement_v1")
        )
        row_vs = next(
            line for line in text.splitlines() if line.startswith("volume_spike_v1")
        )
        row_ss = next(
            line for line in text.splitlines() if line.startswith("short_sell_v1")
        )

        assert "GO" in row_pm
        assert "NOT_VALIDATED" in row_vs
        assert "DISABLED" in row_ss
        assert "rules fireable in at least one reported regime: 1/8" in text

    def test_reports_insufficient_data_verdict(self) -> None:
        RuleConfig.objects.create(
            rule_id="breakout_v1",
            enabled=True,
            validated_regimes={"BULLISH": {"status": "INSUFFICIENT_DATA"}},
        )
        out = StringIO()
        call_command("rule_gate_report", regime="BULLISH", stdout=out)
        row = next(
            line
            for line in out.getvalue().splitlines()
            if line.startswith("breakout_v1")
        )
        assert "INSUFFICIENT_DATA" in row
