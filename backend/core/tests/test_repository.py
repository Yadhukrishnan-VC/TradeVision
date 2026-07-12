"""
Tests for core.repository — cannot instantiate directly; concrete subclass satisfies interface.
"""

import pytest

from core.repository import BaseRepository


class TestBaseRepository:

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseRepository()  # type: ignore[abstract]

    def test_concrete_subclass_satisfies_interface(self) -> None:
        class StringRepo(BaseRepository[str]):
            def get_by_id(self, id): return None
            def create(self, **kwargs): return "created"
            def update(self, id, **kwargs): return "updated"
            def delete(self, id): return True
            def list_all(self, **filters): return []

        repo = StringRepo()
        assert repo.get_by_id("x") is None
        assert repo.create(name="x") == "created"
