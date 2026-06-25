"""DB2 quirks behavior."""

import pytest

from db.plugins.db2.quirks import Db2Quirks


def test_build_snapshot_table_ddl_refuses_db2_snapshot_ddl() -> None:
    with pytest.raises(NotImplementedError):
        Db2Quirks().build_snapshot_table_ddl('"APP"."DBLIFT_SCHEMA_SNAPSHOTS"', 255, 128)
