"""
Unit tests for ObjectOrderer.
"""

import pytest

from core.normalization.object_orderer import ObjectOrderer
from core.sql_model.base import SqlObject, SqlObjectType
from core.sql_model.table import Table
from core.sql_model.view import View

pytestmark = [pytest.mark.unit]


class TestObjectOrderer:
    """Test cases for ObjectOrderer."""

    def test_sort_objects_basic(self):
        """Test basic object sorting."""
        obj1 = SqlObject("zebra", SqlObjectType.TABLE)
        obj2 = SqlObject("apple", SqlObjectType.TABLE)
        obj3 = SqlObject("banana", SqlObjectType.VIEW)

        sorted_objs = ObjectOrderer.sort_objects([obj1, obj2, obj3])

        # Tables come before views
        assert sorted_objs[0].name == "apple"
        assert sorted_objs[1].name == "zebra"
        assert sorted_objs[2].name == "banana"

    def test_sort_by_dependencies_no_dependencies(self):
        """Test sorting with no dependency map falls back to canonical ordering."""
        obj1 = SqlObject("zebra", SqlObjectType.TABLE)
        obj2 = SqlObject("apple", SqlObjectType.TABLE)

        sorted_objs = ObjectOrderer.sort_by_dependencies([obj1, obj2])

        assert sorted_objs[0].name == "apple"
        assert sorted_objs[1].name == "zebra"

    def test_sort_by_dependencies_linear(self):
        """Test sorting with linear dependencies."""
        table_a = Table("table_a", schema="public")
        table_b = Table("table_b", schema="public")
        view_c = View("view_c", query="SELECT * FROM table_b", schema="public")

        dependency_map = {
            "public.table_b": ["public.table_a"],
            "public.view_c": ["public.table_b"],
        }

        sorted_objs = ObjectOrderer.sort_by_dependencies([view_c, table_b, table_a], dependency_map)

        # Should be sorted by dependency depth: table_a (0), table_b (1), view_c (2)
        names = [obj.name for obj in sorted_objs]
        assert names.index("table_a") < names.index("table_b")
        assert names.index("table_b") < names.index("view_c")

    def test_sort_by_dependencies_circular_detection(self):
        """Test that circular dependencies are detected and raise ValueError."""
        table_a = Table("table_a", schema="public")
        table_b = Table("table_b", schema="public")

        # Create circular dependency: A depends on B, B depends on A
        dependency_map = {
            "public.table_a": ["public.table_b"],
            "public.table_b": ["public.table_a"],
        }

        with pytest.raises(ValueError, match="Circular dependency detected"):
            ObjectOrderer.sort_by_dependencies([table_a, table_b], dependency_map)

    def test_sort_by_dependencies_circular_detection_message(self):
        """Test that circular dependency error message includes the cycle path."""
        table_a = Table("table_a", schema="public")
        table_b = Table("table_b", schema="public")

        dependency_map = {
            "public.table_a": ["public.table_b"],
            "public.table_b": ["public.table_a"],
        }

        with pytest.raises(ValueError) as exc_info:
            ObjectOrderer.sort_by_dependencies([table_a, table_b], dependency_map)

        error_msg = str(exc_info.value)
        assert "Circular dependency detected" in error_msg
        assert "public.table_a" in error_msg
        assert "public.table_b" in error_msg

    def test_sort_by_dependencies_self_reference(self):
        """Test that self-referencing dependencies are detected."""
        table_a = Table("table_a", schema="public")

        # Table depends on itself
        dependency_map = {
            "public.table_a": ["public.table_a"],
        }

        with pytest.raises(ValueError, match="Circular dependency detected"):
            ObjectOrderer.sort_by_dependencies([table_a], dependency_map)

    def test_sort_by_dependencies_complex_cycle(self):
        """Test detection of complex cycles (A->B->C->A)."""
        table_a = Table("table_a", schema="public")
        table_b = Table("table_b", schema="public")
        table_c = Table("table_c", schema="public")

        dependency_map = {
            "public.table_a": ["public.table_b"],
            "public.table_b": ["public.table_c"],
            "public.table_c": ["public.table_a"],
        }

        with pytest.raises(ValueError, match="Circular dependency detected"):
            ObjectOrderer.sort_by_dependencies([table_a, table_b, table_c], dependency_map)

    def test_sort_by_dependencies_memoization(self):
        """Test that dependency depths are memoized (no redundant calculations)."""
        table_a = Table("table_a", schema="public")
        table_b = Table("table_b", schema="public")
        view_c = View("view_c", query="SELECT * FROM table_b", schema="public")
        view_d = View("view_d", query="SELECT * FROM table_b", schema="public")

        # Both views depend on table_b, which depends on table_a
        dependency_map = {
            "public.table_b": ["public.table_a"],
            "public.view_c": ["public.table_b"],
            "public.view_d": ["public.table_b"],
        }

        # Should not raise an error and should sort correctly
        sorted_objs = ObjectOrderer.sort_by_dependencies(
            [view_c, view_d, table_b, table_a], dependency_map
        )

        names = [obj.name for obj in sorted_objs]
        # table_a should come first (depth 0)
        assert names[0] == "table_a"
        # table_b should come next (depth 1)
        assert names.index("table_b") < names.index("view_c")
        assert names.index("table_b") < names.index("view_d")
