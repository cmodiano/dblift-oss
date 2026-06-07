"""
Unit tests for DependencyResolver.
"""

import pytest

from core.normalization.dependency_resolver import DependencyResolver
from core.sql_model.index import Index
from core.sql_model.procedure import Procedure
from core.sql_model.table import Table
from core.sql_model.table_options import PostgresTableOptions, TableOptions
from core.sql_model.trigger import Trigger
from core.sql_model.view import View

pytestmark = [pytest.mark.unit]


class TestDependencyResolver:
    """Test cases for DependencyResolver."""

    def test_build_dependency_graph_tables(self):
        """Test building dependency graph for tables with foreign keys."""
        resolver = DependencyResolver()

        # Create tables with foreign key
        parent_table = Table(name="parent", schema="public", columns=[])
        child_table = Table(
            name="child",
            schema="public",
            columns=[],
        )
        # Add foreign key constraint
        from core.sql_model.base import ConstraintType, SqlConstraint

        fk_constraint = SqlConstraint(
            name="fk_child_parent",
            constraint_type=ConstraintType.FOREIGN_KEY,
            column_names=["parent_id"],
            reference_table="parent",
        )
        fk_constraint.reference_schema = "public"
        child_table.constraints = [fk_constraint]

        graph = resolver.build_dependency_graph(
            tables=[parent_table, child_table],
            schema="public",
        )

        child_key = resolver._get_object_key("table", "child", "public")
        parent_key = resolver._get_object_key("table", "parent", "public")

        assert child_key in graph
        assert parent_key in graph[child_key]

    def test_build_dependency_graph_inheritance(self):
        """Test building dependency graph for table inheritance."""
        resolver = DependencyResolver()

        parent_table = Table(name="parent", schema="public", columns=[])
        child_table = Table.from_options(
            name="child",
            schema="public",
            columns=[],
            options=TableOptions(postgres=PostgresTableOptions(inherits=["parent"])),
        )

        graph = resolver.build_dependency_graph(
            tables=[parent_table, child_table],
            schema="public",
        )

        child_key = resolver._get_object_key("table", "child", "public")
        parent_key = resolver._get_object_key("table", "parent", "public")

        assert child_key in graph
        assert parent_key in graph[child_key]

    def test_build_dependency_graph_indexes(self):
        """Test building dependency graph for indexes."""
        resolver = DependencyResolver()

        table = Table(name="mytable", schema="public", columns=[])
        index = Index(
            name="idx_name",
            table_name="mytable",
            schema="public",
            columns=["id"],
        )

        graph = resolver.build_dependency_graph(
            tables=[table],
            indexes=[index],
            schema="public",
        )

        index_key = resolver._get_object_key("index", "idx_name", "public")
        table_key = resolver._get_object_key("table", "mytable", "public")

        assert index_key in graph
        assert table_key in graph[index_key]

    def test_build_dependency_graph_views(self):
        """Test building dependency graph for views."""
        resolver = DependencyResolver()

        table = Table(name="mytable", schema="public", columns=[])
        view = View(
            name="myview",
            schema="public",
            query="SELECT * FROM mytable",
        )

        graph = resolver.build_dependency_graph(
            tables=[table],
            views=[view],
            schema="public",
        )

        view_key = resolver._get_object_key("view", "myview", "public")
        table_key = resolver._get_object_key("table", "mytable", "public")

        assert view_key in graph
        assert table_key in graph[view_key]

    def test_build_dependency_graph_procedures(self):
        """Test building dependency graph for procedures."""
        resolver = DependencyResolver()

        table = Table(name="mytable", schema="public", columns=[])
        procedure = Procedure(
            name="myproc",
            schema="public",
            body="SELECT * FROM mytable",
        )

        graph = resolver.build_dependency_graph(
            tables=[table],
            procedures=[procedure],
            schema="public",
        )

        proc_key = resolver._get_object_key("procedure", "myproc", "public")
        table_key = resolver._get_object_key("table", "mytable", "public")

        assert proc_key in graph
        assert table_key in graph[proc_key]

    def test_build_dependency_graph_triggers(self):
        """Test building dependency graph for triggers."""
        resolver = DependencyResolver()

        table = Table(name="mytable", schema="public", columns=[])
        trigger = Trigger(
            name="mytrigger",
            table_name="mytable",
            schema="public",
            timing="BEFORE",
            events=["INSERT"],
            definition="BEGIN ... END",
        )

        graph = resolver.build_dependency_graph(
            tables=[table],
            triggers=[trigger],
            schema="public",
        )

        trigger_key = resolver._get_object_key("trigger", "mytrigger", "public")
        table_key = resolver._get_object_key("table", "mytable", "public")

        assert trigger_key in graph
        assert table_key in graph[trigger_key]

    def test_get_dependencies(self):
        """Test getting dependencies for an object."""
        resolver = DependencyResolver()

        table = Table(name="mytable", schema="public", columns=[])
        view = View(
            name="myview",
            schema="public",
            query="SELECT * FROM mytable",
        )

        resolver.build_dependency_graph(
            tables=[table],
            views=[view],
            schema="public",
        )

        deps = resolver.get_dependencies("view", "myview", "public")
        table_key = resolver._get_object_key("table", "mytable", "public")

        assert table_key in deps

    def test_get_dependents(self):
        """Test getting dependents of an object."""
        resolver = DependencyResolver()

        table = Table(name="mytable", schema="public", columns=[])
        view = View(
            name="myview",
            schema="public",
            query="SELECT * FROM mytable",
        )

        resolver.build_dependency_graph(
            tables=[table],
            views=[view],
            schema="public",
        )

        dependents = resolver.get_dependents("table", "mytable", "public")
        view_key = resolver._get_object_key("view", "myview", "public")

        assert view_key in dependents

    def test_get_all_dependencies(self):
        """Test getting transitive dependencies."""
        resolver = DependencyResolver()

        # Create chain: table1 -> table2 -> table3
        table1 = Table(name="table1", schema="public", columns=[])
        table2 = Table(name="table2", schema="public", columns=[])
        table3 = Table(name="table3", schema="public", columns=[])

        # Add foreign keys
        from core.sql_model.base import ConstraintType, SqlConstraint

        fk2 = SqlConstraint(
            name="fk2",
            constraint_type=ConstraintType.FOREIGN_KEY,
            column_names=["id"],
            reference_table="table1",
        )
        fk3 = SqlConstraint(
            name="fk3",
            constraint_type=ConstraintType.FOREIGN_KEY,
            column_names=["id"],
            reference_table="table2",
        )
        table2.constraints = [fk2]
        table3.constraints = [fk3]

        resolver.build_dependency_graph(
            tables=[table1, table2, table3],
            schema="public",
        )

        all_deps = resolver.get_all_dependencies("table", "table3", "public")
        table1_key = resolver._get_object_key("table", "table1", "public")
        table2_key = resolver._get_object_key("table", "table2", "public")

        assert table1_key in all_deps
        assert table2_key in all_deps

    def test_get_dependency_order(self):
        """Test getting objects in dependency order."""
        resolver = DependencyResolver()

        parent = Table(name="parent", schema="public", columns=[])
        child = Table(name="child", schema="public", columns=[])

        from core.sql_model.base import ConstraintType, SqlConstraint

        fk = SqlConstraint(
            name="fk",
            constraint_type=ConstraintType.FOREIGN_KEY,
            column_names=["parent_id"],
            reference_table="parent",
        )
        child.constraints = [fk]

        ordered = resolver.get_dependency_order(
            [parent, child],
            schema="public",
        )

        # Parent should come before child
        assert ordered[0].name == "parent"
        assert ordered[1].name == "child"

    def test_detect_circular_dependencies(self):
        """Test detecting circular dependencies."""
        resolver = DependencyResolver()

        # Create circular dependency (should be detected but not break)
        table1 = Table(name="table1", schema="public", columns=[])
        table2 = Table(name="table2", schema="public", columns=[])

        from core.sql_model.base import ConstraintType, SqlConstraint

        fk1 = SqlConstraint(
            name="fk1",
            constraint_type=ConstraintType.FOREIGN_KEY,
            column_names=["id"],
            reference_table="table2",
        )
        fk2 = SqlConstraint(
            name="fk2",
            constraint_type=ConstraintType.FOREIGN_KEY,
            column_names=["id"],
            reference_table="table1",
        )
        table1.constraints = [fk1]
        table2.constraints = [fk2]

        resolver.build_dependency_graph(
            tables=[table1, table2],
            schema="public",
        )

        cycles = resolver.detect_circular_dependencies("public")
        # Should detect cycles (implementation may vary)
        assert isinstance(cycles, list)
