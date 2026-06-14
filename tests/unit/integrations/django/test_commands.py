"""Django management commands + system check, per-test settings via override."""

from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings

pytestmark = pytest.mark.filterwarnings("ignore:Overriding setting DATABASES:UserWarning")


def _settings(tmp_path: Path) -> dict:
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "V1_0_0__t.sql").write_text("CREATE TABLE t (id INTEGER PRIMARY KEY);")
    return {
        "DATABASES": {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(tmp_path / "db.sqlite"),
            }
        },
        "DBLIFT_MIGRATIONS_DIR": str(migrations),
    }


def _memory_settings(tmp_path: Path) -> dict:
    settings = _settings(tmp_path)
    settings["DATABASES"]["default"]["NAME"] = ":memory:"
    return settings


def test_migrate_command_applies(tmp_path):
    with override_settings(**_settings(tmp_path)):
        call_command("dblift_migrate")
        from integrations.django.checks import pending_migrations_check

        assert pending_migrations_check(None) == []


def test_migrate_command_applies_in_memory_sqlite(tmp_path):
    with override_settings(**_memory_settings(tmp_path)):
        call_command("dblift_migrate")
        from integrations.django.checks import pending_migrations_check

        assert pending_migrations_check(None) == []


def test_check_reports_pending_before_migrate(tmp_path):
    with override_settings(**_settings(tmp_path)):
        from integrations.django.checks import pending_migrations_check

        messages = pending_migrations_check(None)
        assert messages and messages[0].id == "dblift.W001"


def test_info_command_runs(tmp_path):
    with override_settings(**_settings(tmp_path)):
        call_command("dblift_info")


def test_dblift_commands_skip_system_checks():
    from integrations.django.management.commands.dblift_info import Command as InfoCommand
    from integrations.django.management.commands.dblift_migrate import Command as MigrateCommand
    from integrations.django.management.commands.dblift_validate import Command as ValidateCommand

    assert MigrateCommand.requires_system_checks == []
    assert ValidateCommand.requires_system_checks == []
    assert InfoCommand.requires_system_checks == []


def test_get_client_reuses_engine_for_same_settings(tmp_path):
    with override_settings(**_settings(tmp_path)):
        from integrations.django._client import get_client

        first = get_client()
        second = get_client()
        try:
            assert first.provider._external_engine is second.provider._external_engine
        finally:
            first.close()
            second.close()
