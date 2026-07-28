from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.rules.base_rule import RuleSeverity
from apps.rule_engine.domain.entities import RuleFiring
from apps.rule_engine.infrastructure.models import RuleConfig, RuleExecution
from apps.rule_engine.infrastructure.repositories import (
    RuleConfigRepository,
    RuleExecutionRepository,
)

pytestmark = pytest.mark.django_db


class TestRuleConfigRepository:
    def test_create_and_get_by_id(self) -> None:
        repo = RuleConfigRepository()
        config = RuleConfig(
            rule_id="test_rule_v1",
            enabled=True,
            parameters={"threshold": "2.0"},
        )
        created = repo.create(config)

        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.rule_id == "test_rule_v1"
        assert fetched.enabled is True
        assert fetched.parameters == {"threshold": "2.0"}

    def test_create_and_get_by_rule_id(self) -> None:
        repo = RuleConfigRepository()
        config = RuleConfig(rule_id="my_rule_v2", enabled=False)
        repo.create(config)

        fetched = repo.get_by_rule_id("my_rule_v2")
        assert fetched is not None
        assert fetched.rule_id == "my_rule_v2"
        assert fetched.enabled is False

    def test_get_by_rule_id_returns_none_when_missing(self) -> None:
        repo = RuleConfigRepository()
        assert repo.get_by_rule_id("nonexistent") is None

    def test_get_by_id_returns_none_when_missing(self) -> None:
        repo = RuleConfigRepository()
        assert repo.get_by_id(uuid.uuid4()) is None

    def test_list_with_filters(self) -> None:
        repo = RuleConfigRepository()
        repo.create(RuleConfig(rule_id="rule_a", enabled=True))
        repo.create(RuleConfig(rule_id="rule_b", enabled=True))
        repo.create(RuleConfig(rule_id="rule_c", enabled=False))

        enabled_configs = repo.list(enabled=True)
        assert len(enabled_configs) == 2

        disabled_configs = repo.list(enabled=False)
        assert len(disabled_configs) == 1

    def test_list_no_filters_returns_all(self) -> None:
        repo = RuleConfigRepository()
        repo.create(RuleConfig(rule_id="rule_x", enabled=True))
        repo.create(RuleConfig(rule_id="rule_y", enabled=False))

        all_configs = repo.list()
        assert len(all_configs) == 2

    def test_update(self) -> None:
        repo = RuleConfigRepository()
        config = repo.create(RuleConfig(rule_id="updatable_rule", enabled=True))

        config.enabled = False
        config.parameters = {"new_param": "value"}
        updated = repo.update(config)

        assert updated.enabled is False
        assert updated.parameters == {"new_param": "value"}

        fetched = repo.get_by_id(config.id)
        assert fetched is not None
        assert fetched.enabled is False

    def test_delete(self) -> None:
        repo = RuleConfigRepository()
        config = repo.create(RuleConfig(rule_id="deletable_rule", enabled=True))
        config_id = config.id

        repo.delete(config_id)
        assert repo.get_by_id(config_id) is None

    def test_exists(self) -> None:
        repo = RuleConfigRepository()
        config = repo.create(RuleConfig(rule_id="exists_rule", enabled=True))
        assert repo.exists(config.id) is True
        assert repo.exists(uuid.uuid4()) is False

    def test_count(self) -> None:
        repo = RuleConfigRepository()
        repo.create(RuleConfig(rule_id="count_a", enabled=True))
        repo.create(RuleConfig(rule_id="count_b", enabled=True))
        repo.create(RuleConfig(rule_id="count_c", enabled=False))

        assert repo.count() == 3
        assert repo.count(enabled=True) == 2
        assert repo.count(enabled=False) == 1

    def test_severity_override(self) -> None:
        repo = RuleConfigRepository()
        config = repo.create(
            RuleConfig(rule_id="severity_rule", enabled=True, severity_override="CRITICAL")
        )
        assert config.severity_override == "CRITICAL"

        fetched = repo.get_by_rule_id("severity_rule")
        assert fetched is not None
        assert fetched.severity_override == "CRITICAL"


class TestRuleExecutionRepository:
    def test_create_and_get_by_id(self) -> None:
        repo = RuleExecutionRepository()
        execution = RuleExecution(
            analysis_event_id=uuid.uuid4(),
            rule_id="test_rule_v1",
            symbol="RELIANCE",
            severity="HIGH",
            trigger_data={"change_pct": "3.5"},
        )
        created = repo.create(execution)

        fetched = repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.rule_id == "test_rule_v1"
        assert fetched.symbol == "RELIANCE"
        assert fetched.severity == "HIGH"
        assert fetched.trigger_data == {"change_pct": "3.5"}

    def test_get_by_id_returns_none_when_missing(self) -> None:
        repo = RuleExecutionRepository()
        assert repo.get_by_id(uuid.uuid4()) is None

    def test_list_with_filters(self) -> None:
        repo = RuleExecutionRepository()
        eid = uuid.uuid4()
        repo.create(RuleExecution(analysis_event_id=eid, rule_id="r1", symbol="A", severity="HIGH"))
        repo.create(RuleExecution(analysis_event_id=uuid.uuid4(), rule_id="r1", symbol="B", severity="MEDIUM"))
        repo.create(RuleExecution(analysis_event_id=uuid.uuid4(), rule_id="r2", symbol="A", severity="LOW"))

        r1_execs = repo.list(rule_id="r1")
        assert len(r1_execs) == 2

        symbol_a_execs = repo.list(symbol="A")
        assert len(symbol_a_execs) == 2

        r1_a_execs = repo.list(rule_id="r1", symbol="A")
        assert len(r1_a_execs) == 1

    def test_update(self) -> None:
        repo = RuleExecutionRepository()
        execution = repo.create(
            RuleExecution(
                analysis_event_id=uuid.uuid4(),
                rule_id="update_test",
                symbol="TEST",
                severity="LOW",
            )
        )

        execution.severity = "HIGH"
        execution.trigger_data = {"key": "value"}
        updated = repo.update(execution)

        assert updated.severity == "HIGH"
        assert updated.trigger_data == {"key": "value"}

    def test_delete(self) -> None:
        repo = RuleExecutionRepository()
        execution = repo.create(
            RuleExecution(analysis_event_id=uuid.uuid4(), rule_id="del_test", symbol="X", severity="LOW")
        )
        exec_id = execution.id

        repo.delete(exec_id)
        assert repo.get_by_id(exec_id) is None

    def test_exists(self) -> None:
        repo = RuleExecutionRepository()
        execution = repo.create(
            RuleExecution(analysis_event_id=uuid.uuid4(), rule_id="exists_test", symbol="X", severity="LOW")
        )
        assert repo.exists(execution.id) is True
        assert repo.exists(uuid.uuid4()) is False

    def test_count(self) -> None:
        repo = RuleExecutionRepository()
        repo.create(RuleExecution(analysis_event_id=uuid.uuid4(), rule_id="c1", symbol="A", severity="HIGH"))
        repo.create(RuleExecution(analysis_event_id=uuid.uuid4(), rule_id="c1", symbol="B", severity="MEDIUM"))

        assert repo.count() == 2
        assert repo.count(rule_id="c1") == 2
        assert repo.count(rule_id="nonexistent") == 0

    def test_create_from_firing_creates_execution(self) -> None:
        repo = RuleExecutionRepository()
        analysis_event_id = uuid.uuid4()
        firing = RuleFiring(
            rule_id="price_movement_v1",
            event_type="price_movement",
            severity=RuleSeverity.HIGH,
            symbol="RELIANCE",
            trigger_data={"change_pct": "3.5"},
            analysis_event_id=analysis_event_id,
            occurred_at=datetime.now(timezone.utc),
        )

        execution = repo.create_from_firing(firing, str(analysis_event_id))

        assert execution is not None
        assert execution.rule_id == "price_movement_v1"
        assert execution.symbol == "RELIANCE"
        assert execution.severity == "HIGH"
        assert execution.trigger_data == {"change_pct": "3.5"}
        assert execution.published_event_id is None

    def test_create_from_firing_idempotent_returns_none_on_duplicate(self) -> None:
        repo = RuleExecutionRepository()
        analysis_event_id = uuid.uuid4()
        firing = RuleFiring(
            rule_id="dup_rule",
            event_type="test_event",
            severity=RuleSeverity.LOW,
            symbol="TEST",
            trigger_data={},
            analysis_event_id=analysis_event_id,
            occurred_at=datetime.now(timezone.utc),
        )

        first = repo.create_from_firing(firing, str(analysis_event_id))
        assert first is not None

        second = repo.create_from_firing(firing, str(analysis_event_id))
        assert second is None

        assert repo.count(analysis_event_id=analysis_event_id) == 1

    def test_create_from_firing_allows_different_rule_id_same_event(self) -> None:
        repo = RuleExecutionRepository()
        analysis_event_id = uuid.uuid4()

        firing_a = RuleFiring(
            rule_id="rule_a",
            event_type="event_a",
            severity=RuleSeverity.LOW,
            symbol="TEST",
            trigger_data={},
            analysis_event_id=analysis_event_id,
            occurred_at=datetime.now(timezone.utc),
        )
        firing_b = RuleFiring(
            rule_id="rule_b",
            event_type="event_b",
            severity=RuleSeverity.HIGH,
            symbol="TEST",
            trigger_data={},
            analysis_event_id=analysis_event_id,
            occurred_at=datetime.now(timezone.utc),
        )

        first = repo.create_from_firing(firing_a, str(analysis_event_id))
        assert first is not None

        second = repo.create_from_firing(firing_b, str(analysis_event_id))
        assert second is not None

        assert repo.count(analysis_event_id=analysis_event_id) == 2

    def test_create_from_firing_allows_same_rule_different_event(self) -> None:
        repo = RuleExecutionRepository()
        firing = RuleFiring(
            rule_id="same_rule",
            event_type="test",
            severity=RuleSeverity.LOW,
            symbol="TEST",
            trigger_data={},
            analysis_event_id=uuid.uuid4(),
            occurred_at=datetime.now(timezone.utc),
        )

        first = repo.create_from_firing(firing, str(uuid.uuid4()))
        assert first is not None

        second = repo.create_from_firing(firing, str(uuid.uuid4()))
        assert second is not None

        assert repo.count(rule_id="same_rule") == 2

    def test_mark_published_updates_correct_record(self) -> None:
        repo = RuleExecutionRepository()
        analysis_event_id = uuid.uuid4()
        published_event_id = uuid.uuid4()

        execution = repo.create(
            RuleExecution(
                analysis_event_id=analysis_event_id,
                rule_id="pub_test",
                symbol="X",
                severity="HIGH",
            )
        )

        repo.mark_published(analysis_event_id, published_event_id)

        fetched = repo.get_by_id(execution.id)
        assert fetched is not None
        assert fetched.published_event_id == published_event_id

    def test_mark_published_does_not_update_already_published(self) -> None:
        repo = RuleExecutionRepository()
        analysis_event_id = uuid.uuid4()
        first_published = uuid.uuid4()
        second_published = uuid.uuid4()

        execution = repo.create(
            RuleExecution(
                analysis_event_id=analysis_event_id,
                rule_id="pub_test_2",
                symbol="X",
                severity="HIGH",
            )
        )

        repo.mark_published(analysis_event_id, first_published)
        repo.mark_published(analysis_event_id, second_published)

        fetched = repo.get_by_id(execution.id)
        assert fetched is not None
        assert fetched.published_event_id == first_published

    def test_mark_published_updates_all_unpublished_for_event(self) -> None:
        repo = RuleExecutionRepository()
        analysis_event_id = uuid.uuid4()
        published_event_id = uuid.uuid4()

        repo.create(
            RuleExecution(analysis_event_id=analysis_event_id, rule_id="r1", symbol="X", severity="HIGH")
        )
        repo.create(
            RuleExecution(analysis_event_id=analysis_event_id, rule_id="r2", symbol="X", severity="LOW")
        )

        repo.mark_published(analysis_event_id, published_event_id)

        for ex in repo.list(analysis_event_id=analysis_event_id):
            assert ex.published_event_id == published_event_id
