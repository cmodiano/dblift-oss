"""Tests for story 20-9: removal of redundant dialect.lower() calls."""

import inspect

import pytest

from core.migration.sql import sql_analyzer as sql_analyzer_mod
from core.migration.sql import sql_insights as sql_insights_mod
from core.migration.sql.sql_analyzer import SqlAnalyzer
from core.migration.sql.sql_insights import SqlInsights

pytestmark = [pytest.mark.unit]


def test_no_redundant_dialect_lower_in_sql_analyzer():
    """AC#2 : self.dialect est deja normalise en __init__, .lower() redondant."""
    source = inspect.getsource(sql_analyzer_mod.SqlAnalyzer)
    assert (
        "self.dialect.lower()" not in source
    ), "Redundant self.dialect.lower() found in SqlAnalyzer"


def test_sql_insights_available_uses_self_dialect():
    """AC#3 : self.available doit utiliser self.dialect, pas dialect.lower()."""
    source = inspect.getsource(sql_insights_mod.SqlInsights.__init__)
    lines = source.splitlines()
    dialect_assigned = False
    for line in lines:
        stripped = line.strip()
        if "self.dialect = dialect.lower()" in stripped:
            dialect_assigned = True
        if (
            dialect_assigned
            and "dialect.lower()" in stripped
            and "self.dialect = dialect.lower()" not in stripped
        ):
            raise AssertionError(
                f"Redundant dialect.lower() found after self.dialect assignment: {line!r}"
            )
    assert dialect_assigned, (
        "self.dialect = dialect.lower() assignment not found in SqlInsights.__init__ — "
        "the structural guard above is vacuously passing"
    )


def test_sql_analyzer_sqlserver_dialect_recognized():
    """Regression : le split SQL Server GO-splitting fonctionne avec dialect='sqlserver'."""
    analyzer = SqlAnalyzer(dialect="sqlserver")
    sql = "SELECT 1\nGO\nSELECT 2"
    stmts = analyzer.split_statements(sql)
    assert len(stmts) == 2, f"Expected 2 statements after GO split, got {len(stmts)}: {stmts}"


def test_sql_insights_not_available_for_db2():
    """Regression : db2 dialect -> available=False (self.dialect != 'db2' check)."""
    insights = SqlInsights(dialect="db2")
    assert not insights.available


def test_sql_insights_available_for_supported_dialect():
    """AC#3 positif : dialect supporté -> available == SQLGLOT_AVAILABLE."""
    from core.migration.sql.sql_insights import SQLGLOT_AVAILABLE

    insights = SqlInsights(dialect="mysql")
    assert (
        insights.available == SQLGLOT_AVAILABLE
    ), f"SqlInsights(dialect='mysql').available should be {SQLGLOT_AVAILABLE}"
