"""Oracle quirks behavior."""

import pytest

from db.plugins.oracle.quirks import OracleQuirks


def test_build_snapshot_table_ddl_is_not_owned_by_oracle_plugin() -> None:
    with pytest.raises(NotImplementedError):
        OracleQuirks().build_snapshot_table_ddl('"APP"."DBLIFT_SCHEMA_SNAPSHOTS"', 255, 128)
