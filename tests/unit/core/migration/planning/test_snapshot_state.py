import json

import pytest


def _write_snapshot(tmp_path, metadata):
    path = tmp_path / "snapshot.json"
    path.write_text(
        json.dumps(
            {
                "tables": [],
                "views": [],
                "indexes": [],
                "metadata": metadata,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_loads_legacy_applied_versions(tmp_path):
    from core.migration.planning.snapshot_state import SnapshotMigrationState

    path = _write_snapshot(
        tmp_path,
        {
            "migration": {
                "last_version": "2",
                "applied_versions": ["1", "2"],
                "repeatables": [],
            }
        },
    )

    state = SnapshotMigrationState.from_path(path)

    assert state.last_version == "2"
    assert state.applied_versions == {"1", "2"}
    assert state.applied_checksums_by_version == {}
    assert state.is_version_applied("1") is True
    assert state.is_version_applied("3") is False
    assert state.has_applied_manifest is False


def test_loads_enriched_applied_manifest(tmp_path):
    from core.migration.planning.snapshot_state import SnapshotMigrationState

    path = _write_snapshot(
        tmp_path,
        {
            "migration": {
                "last_version": "2",
                "applied": [
                    {
                        "version": "1",
                        "script": "V1__init.sql",
                        "checksum": 111,
                        "installed_rank": 1,
                        "installed_on": "2026-05-20T10:00:00",
                        "type": "SQL",
                        "success": True,
                    },
                    {
                        "version": "2",
                        "script": "V2__users.sql",
                        "checksum": 222,
                        "installed_rank": 2,
                        "installed_on": "2026-05-21T10:00:00",
                        "type": "SQL",
                        "success": True,
                    },
                ],
                "repeatables": [
                    {
                        "script": "R__refresh_view.sql",
                        "checksum": 333,
                        "installed_rank": 3,
                        "installed_on": "2026-05-22T10:00:00",
                    }
                ],
            }
        },
    )

    state = SnapshotMigrationState.from_path(path)

    assert state.applied_versions == {"1", "2"}
    assert state.applied_checksums_by_version["2"] == 222
    assert state.applied_by_version["1"].script == "V1__init.sql"
    assert state.repeatables_by_script["R__refresh_view.sql"].checksum == 333
    assert state.has_applied_manifest is True


def test_empty_enriched_manifest_does_not_fall_back_to_legacy_versions(tmp_path):
    from core.migration.planning.snapshot_state import SnapshotMigrationState

    path = _write_snapshot(
        tmp_path,
        {
            "migration": {
                "last_version": "2",
                "applied_versions": ["1", "2"],
                "applied": [],
                "repeatables": [],
            }
        },
    )

    state = SnapshotMigrationState.from_path(path)

    assert state.applied_versions == set()
    assert state.is_version_applied("1") is False
    assert state.has_applied_manifest is True


def test_invalid_json_error_mentions_snapshot_path(tmp_path):
    from core.migration.planning.snapshot_state import SnapshotMigrationState

    path = tmp_path / "snapshot.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(ValueError, match=str(path)):
        SnapshotMigrationState.from_path(path)


def test_missing_migration_metadata_error_mentions_snapshot_path(tmp_path):
    from core.migration.planning.snapshot_state import SnapshotMigrationState

    path = _write_snapshot(tmp_path, {"dialect": "postgresql"})

    with pytest.raises(ValueError, match=str(path)):
        SnapshotMigrationState.from_path(path)
