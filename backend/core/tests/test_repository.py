"""
Tests for core.repository — cannot instantiate directly; concrete subclass satisfies interface.
"""

import uuid

import pytest

from core.repository import BaseRepository


class TestBaseRepository:

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseRepository()  # type: ignore[abstract]

    def test_concrete_subclass_satisfies_interface(self) -> None:
        class StringRepo(BaseRepository[str]):
            def get_by_id(self, entity_id: uuid.UUID) -> str | None:
                return None

            def list(self, **filters) -> list[str]:
                return []

            def create(self, entity: str) -> str:
                return "created"

            def update(self, entity: str) -> str:
                return "updated"

            def delete(self, entity_id: uuid.UUID) -> None:
                pass

            def exists(self, entity_id: uuid.UUID) -> bool:
                return False

            def count(self, **filters) -> int:
                return 0

        repo = StringRepo()
        assert repo.get_by_id(uuid.uuid4()) is None
        assert repo.create("x") == "created"
        assert repo.list() == []
        assert repo.exists(uuid.uuid4()) is False
        assert repo.count() == 0
