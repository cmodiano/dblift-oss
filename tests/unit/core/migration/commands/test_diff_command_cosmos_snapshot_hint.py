"""CosmosDB diff should describe database-stored snapshots as enabled.

CosmosDB does not support traditional transactions, but snapshot capture is
gated by ``supports_snapshots()``, not ``supports_transactions()``. A missing
stored snapshot should therefore tell users to run migrations or provide a
``--snapshot-model`` file, not claim CosmosDB cannot auto-capture snapshots.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.unit
class TestDiffCommandCosmosSnapshotHint:
    """Source-level assertions on the diff_command branch.

    We assert on source because the execute() method has ~15 collaborators;
    mocking the entire pipeline just to reach one branch is brittle. The
    branch is small and localized, so a source-level check is adequate.
    """

    def _src(self) -> str:
        path = Path("core/migration/commands/diff_command.py")
        return path.read_text(encoding="utf-8")

    def test_cosmos_branch_mentions_migrate_and_snapshot_model(self):
        src = self._src()
        # NoSQL dialects should support both database-stored snapshots and file models.
        assert "Run migrations to capture" in src
        assert "database-stored snapshot" in src
        assert "--snapshot-model" in src

    def test_cosmos_branch_does_not_claim_snapshots_are_disabled(self):
        src = self._src()
        assert "do not auto-capture snapshots" not in src
        assert "never auto-captures snapshots" not in src

    def test_nosql_branch_uses_quirks_is_nosql(self):
        src = self._src()
        # Branch must use the quirks system, not hardcoded dialect strings.
        assert "db_type" in src
        assert "is_nosql" in src
        assert all(tok not in src for tok in ('"cosmosdb"', '"nosql"'))

    def test_generic_branch_retained_for_sql_providers(self):
        """The original SQL-path message must still exist for relational DBs."""
        src = self._src()
        assert "Run migrations or provide --snapshot-model" in src
