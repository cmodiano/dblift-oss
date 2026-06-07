from unittest.mock import Mock

from core.logger.results import MigrateResult, MigrationInfo
from core.preflight.replay import MigrationReplayRunner


def _migrate_result(*scripts):
    result = MigrateResult()
    for index, script in enumerate(scripts, start=1):
        result.add_migration(
            MigrationInfo(
                script=script,
                version=str(index),
                description=script,
                status="SUCCESS",
            )
        )
    result.complete()
    return result


def test_full_replay_runs_dblift_migrate_against_empty_container():
    client = Mock()
    client.migrate.return_value = _migrate_result(
        "V1__init.sql",
        "V2__customers.sql",
        "V1001__invoice.sql",
    )

    result = MigrationReplayRunner(client=client, log=Mock()).replay(scope="all")

    assert result.success is True
    assert result.scope == "all"
    assert result.scripts == ["V1__init.sql", "V2__customers.sql", "V1001__invoice.sql"]
    client.migrate.assert_called_once()


def test_planned_replay_still_uses_migrate_and_relies_on_container_history():
    client = Mock()
    client.migrate.return_value = _migrate_result("V1001__invoice.sql")

    result = MigrationReplayRunner(client=client, log=Mock()).replay(scope="planned")

    assert result.success is True
    assert result.scope == "planned"
    assert result.scripts == ["V1001__invoice.sql"]
    client.migrate.assert_called_once()


def test_replay_result_records_failed_migrate_result():
    failed = MigrateResult()
    failed.set_error("syntax error near invoice")
    failed.complete()
    client = Mock()
    client.migrate.return_value = failed

    result = MigrationReplayRunner(client=client, log=Mock()).replay(scope="all")

    assert result.success is False
    assert result.error_message == "syntax error near invoice"
