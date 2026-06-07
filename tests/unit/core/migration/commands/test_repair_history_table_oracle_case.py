"""BUG-03 regression: Oracle repair uses uppercase history-table identifier.

Before ADR-0015, ``repair``'s failed-migration delete path built its
SQL as ``"DBLIFT_TEST"."dblift_schema_history"`` — ANSI-quoted
lowercase. Oracle stores the table as unquoted ``DBLIFT_SCHEMA_HISTORY``
(folded uppercase) so the quoted lowercase reference resolves to a
literally-named table that does not exist → ORA-00942.

This test pins the fix: the SQL routed to the provider uses the
normalized (upper-cased) identifier.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.logger.results import RepairResult
from core.migration.commands.repair_command import RepairCommand


class _OracleProviderStub:
    """Mirrors the part of the real Oracle provider the DELETE path touches."""

    def __init__(self):
        self.statements: list[str] = []

    def get_normalized_object_name(self, name: str) -> str:
        return name.upper()

    def get_schema_qualified_name(self, schema: str, table: str) -> str:
        # Real base-provider quoting: ANSI double-quotes both halves.
        # This is where the lowercase bug surfaced — quoted lowercase
        # is a LITERAL lowercase identifier to Oracle.
        return f'"{schema}"."{table}"'

    def _ensure_connection(self):
        return None

    def supports_transactions(self) -> bool:
        return True

    def execute_statement(self, sql, params=None, return_generated_keys=False):
        self.statements.append(sql)
        return 1


def _make_repair_command() -> RepairCommand:
    """Bypass BaseCommand.__init__; we only exercise _delete_failed_migration_entry."""
    cmd = RepairCommand.__new__(RepairCommand)
    cmd.log = MagicMock()
    cmd.config = SimpleNamespace(database=SimpleNamespace(schema="DBLIFT_TEST", type="oracle"))
    cmd.provider = _OracleProviderStub()

    history_manager = MagicMock()
    history_manager.history_table = "dblift_schema_history"
    history_manager.normalized_history_table = "DBLIFT_SCHEMA_HISTORY"
    cmd.history_manager = history_manager
    return cmd


@pytest.mark.unit
class TestRepairUsesNormalizedHistoryTableForOracle:
    def test_delete_sql_targets_uppercase_table(self):
        """The DELETE must reference the upper-cased form, not the lowercase one."""
        cmd = _make_repair_command()

        repair = {
            "script": "V1__create_users.sql",
            "version": "1",
            "original_type": None,
        }

        cmd._delete_failed_migration_entry(repair, RepairResult())

        assert cmd.provider.statements, "expected a DELETE statement to be executed"
        delete_sql = cmd.provider.statements[0]
        assert (
            '"DBLIFT_TEST"."DBLIFT_SCHEMA_HISTORY"' in delete_sql
        ), f"DELETE must target the uppercase table on Oracle; got: {delete_sql!r}"
        # And definitely not the lowercase form that ORA-00942's on.
        assert '"dblift_schema_history"' not in delete_sql
