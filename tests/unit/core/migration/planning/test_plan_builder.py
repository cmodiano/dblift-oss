from types import SimpleNamespace


def _write(path, content="select 1;\n"):
    path.write_text(content, encoding="utf-8")
    return path


def _state(snapshot_path, *, applied=None, repeatables=None):
    from core.migration.planning.snapshot_state import SnapshotMigrationState

    return SnapshotMigrationState(
        snapshot_path=snapshot_path,
        metadata={"migration": {}},
        last_version=None,
        applied_versions={str(item.version) for item in applied or [] if item.version},
        applied_by_version={str(item.version): item for item in applied or [] if item.version},
        repeatables_by_script={item.script: item for item in repeatables or []},
        has_applied_manifest=applied is not None,
    )


def _builder(tmp_path, snapshot_state, **kwargs):
    from core.logger import NullLog
    from core.migration.planning.plan_builder import PlanBuilder
    from core.migration.scripting.migration_script_manager import MigrationScriptManager

    return PlanBuilder(
        scripts_dir=tmp_path,
        snapshot_state=snapshot_state,
        script_manager=MigrationScriptManager(NullLog()),
        dialect="postgresql",
        **kwargs,
    )


def test_builds_pending_versioned_migrations(tmp_path):
    _write(tmp_path / "V1__init.sql")
    _write(tmp_path / "V2__users.sql")
    _write(tmp_path / "V3__orders.sql")
    snapshot_state = _state(
        tmp_path / "snapshot.json",
        applied=[
            SimpleNamespace(version="1", script="V1__init.sql", checksum=None),
            SimpleNamespace(version="2", script="V2__users.sql", checksum=None),
        ],
    )

    plan = _builder(tmp_path, snapshot_state, skip_validate_sql=True).build()

    assert [m.version for m in plan.pending] == ["3"]
    assert plan.already_applied_count == 2
    assert plan.has_errors is False


def test_python_versioned_migrations_use_snapshot_state(tmp_path):
    _write(tmp_path / "V1__load_reference_data.py", "def migrate(ctx): pass\n")
    _write(tmp_path / "V2__users.sql")
    snapshot_state = _state(
        tmp_path / "snapshot.json",
        applied=[
            SimpleNamespace(version="1", script="V1__load_reference_data.py", checksum=None),
        ],
    )

    plan = _builder(tmp_path, snapshot_state, skip_validate_sql=True).build()

    assert [m.script for m in plan.pending] == ["V2__users.sql"]
    assert plan.already_applied_count == 1


def test_detects_checksum_drift_for_applied_versioned_migration(tmp_path):
    _write(tmp_path / "V1__init.sql")
    snapshot_state = _state(
        tmp_path / "snapshot.json",
        applied=[SimpleNamespace(version="1", script="V1__init.sql", checksum=222)],
    )

    plan = _builder(tmp_path, snapshot_state, skip_validate_sql=True).build()

    assert len(plan.checksum_drift) == 1
    assert plan.checksum_drift[0].version == "1"
    assert plan.checksum_drift[0].expected_checksum == 222
    assert plan.checksum_drift[0].actual_checksum != 222
    assert plan.has_errors is True


def test_detects_repeatable_migrations_with_changed_checksum(tmp_path):
    _write(tmp_path / "R__refresh_view.sql")
    from core.migration.planning.models import AppliedRepeatableState

    snapshot_state = _state(
        tmp_path / "snapshot.json",
        applied=[],
        repeatables=[
            AppliedRepeatableState(
                script="R__refresh_view.sql",
                checksum=111,
                installed_rank=1,
                installed_on="2026-05-26T10:00:00",
            )
        ],
    )

    plan = _builder(tmp_path, snapshot_state, skip_validate_sql=True).build()

    assert [m.script for m in plan.repeatables_pending] == ["R__refresh_view.sql"]


def test_sql_validation_defaults_to_pending_migrations(tmp_path, monkeypatch):
    _write(tmp_path / "V1__bad_but_already_applied.sql", "invalid")
    _write(tmp_path / "V2__pending.sql", "select 1;")
    snapshot_state = _state(
        tmp_path / "snapshot.json",
        applied=[
            SimpleNamespace(
                version="1",
                script="V1__bad_but_already_applied.sql",
                checksum=None,
            )
        ],
    )
    seen = []

    class FakeValidator:
        def __init__(self, dialect, validation_config=None):
            pass

        def validate_files(self, files):
            seen.extend(path.name for path in files)
            return SimpleNamespace(
                files_checked=len(files),
                error_count=0,
                warning_count=0,
                violations=[],
            )

        def should_fail(self, result):
            return False

    monkeypatch.setattr("core.migration.planning.plan_builder.SqlValidator", FakeValidator)

    plan = _builder(tmp_path, snapshot_state).build()

    assert seen == ["V2__pending.sql"]
    assert plan.sql_validation.files_checked == 1
    assert plan.sql_validation.status == "PASS"


def test_sql_validation_failure_fails_plan(tmp_path, monkeypatch):
    _write(tmp_path / "V1__pending.sql", "broken")
    snapshot_state = _state(tmp_path / "snapshot.json", applied=[])

    class FakeValidator:
        def __init__(self, dialect, validation_config=None):
            pass

        def validate_files(self, files):
            return SimpleNamespace(
                files_checked=len(files),
                error_count=1,
                warning_count=0,
                violations=[
                    SimpleNamespace(
                        rule_id="SYN001",
                        severity=SimpleNamespace(value="error"),
                        source=SimpleNamespace(value="syntax"),
                        message="syntax error",
                        file_path=files[0],
                        line=4,
                    )
                ],
            )

        def should_fail(self, result):
            return True

    monkeypatch.setattr("core.migration.planning.plan_builder.SqlValidator", FakeValidator)

    plan = _builder(tmp_path, snapshot_state).build()

    assert plan.sql_validation.status == "FAIL"
    assert plan.sql_validation.findings[0]["severity"] == "error"
    assert plan.sql_validation.findings[0]["code"] == "SYN001"
    assert plan.sql_validation.findings[0]["details"] == {"source": "syntax"}
    assert plan.sql_validation.findings[0]["line"] == 4
    assert plan.has_errors is True
    assert "validate-sql failed" in plan.errors[0]


def test_sql_validation_all_scope_validates_all_sql_migrations(tmp_path, monkeypatch):
    _write(tmp_path / "V1__applied.sql")
    _write(tmp_path / "V2__pending.sql")
    _write(tmp_path / "R__repeatable.sql")
    snapshot_state = _state(
        tmp_path / "snapshot.json",
        applied=[SimpleNamespace(version="1", script="V1__applied.sql", checksum=None)],
    )
    seen = []

    class FakeValidator:
        def __init__(self, dialect, validation_config=None):
            pass

        def validate_files(self, files):
            seen.extend(path.name for path in files)
            return SimpleNamespace(
                files_checked=len(files),
                error_count=0,
                warning_count=0,
                violations=[],
            )

        def should_fail(self, result):
            return False

    monkeypatch.setattr("core.migration.planning.plan_builder.SqlValidator", FakeValidator)

    plan = _builder(tmp_path, snapshot_state, validate_scope="all").build()

    assert seen == ["V1__applied.sql", "V2__pending.sql", "R__repeatable.sql"]
    assert plan.sql_validation.files_checked == 3
