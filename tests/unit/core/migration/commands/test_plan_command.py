from types import SimpleNamespace
from unittest.mock import MagicMock


def _context():
    from core.migration.commands.base_command import BaseCommandContext

    config = SimpleNamespace(
        database=SimpleNamespace(type="postgresql", schema="public"),
        validation=SimpleNamespace(),
    )
    return BaseCommandContext(
        config=config,
        log=MagicMock(),
        provider=MagicMock(),
        script_manager=MagicMock(),
        history_manager=MagicMock(),
        validator=MagicMock(),
        execution_engine=MagicMock(),
        migration_helpers=MagicMock(),
        state_manager=MagicMock(),
        migration_ui=MagicMock(),
        migration_rules=MagicMock(),
    )


def test_plan_command_returns_plan_result(tmp_path, monkeypatch):
    from core.migration.commands.plan_command import PlanCommand
    from core.migration.planning.models import PlanData, SqlValidationSummary

    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        '{"metadata":{"migration":{"applied_versions":[],"repeatables":[]}}}',
        encoding="utf-8",
    )

    class FakeBuilder:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def build(self):
            return PlanData(
                snapshot_model=str(snapshot),
                target_last_version=None,
                target_installed_rank=None,
                pending=[],
                repeatables_pending=[],
                checksum_drift=[],
                already_applied_count=0,
                warnings=[],
                errors=[],
                sql_validation=SqlValidationSummary(
                    enabled=False,
                    scope="pending",
                    status="SKIPPED",
                ),
            )

    monkeypatch.setattr("core.migration.commands.plan_command.PlanBuilder", FakeBuilder)

    result = PlanCommand(_context()).execute(
        scripts_dir=tmp_path,
        snapshot_model=snapshot,
        skip_validate_sql=True,
    )

    assert result.snapshot_model == str(snapshot)
    assert result.success is True


def test_plan_command_does_not_touch_database(tmp_path, monkeypatch):
    from core.migration.commands.plan_command import PlanCommand
    from core.migration.planning.models import PlanData, SqlValidationSummary

    ctx = _context()
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        '{"metadata":{"migration":{"applied_versions":[],"repeatables":[]}}}',
        encoding="utf-8",
    )

    class FakeBuilder:
        def __init__(self, **kwargs):
            pass

        def build(self):
            return PlanData(
                snapshot_model=str(snapshot),
                target_last_version=None,
                target_installed_rank=None,
                pending=[],
                repeatables_pending=[],
                checksum_drift=[],
                already_applied_count=0,
                warnings=[],
                errors=[],
                sql_validation=SqlValidationSummary(
                    enabled=False,
                    scope="pending",
                    status="SKIPPED",
                ),
            )

    monkeypatch.setattr("core.migration.commands.plan_command.PlanBuilder", FakeBuilder)

    PlanCommand(ctx).execute(scripts_dir=tmp_path, snapshot_model=snapshot)

    ctx.provider.ensure_connection.assert_not_called()
    ctx.history_manager.create_schema_and_history_table.assert_not_called()
