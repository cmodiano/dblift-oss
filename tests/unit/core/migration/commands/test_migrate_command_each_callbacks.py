"""Tests for per-migration callback dispatch."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.logger.results import MigrateResult
from core.migration.commands.migrate_command import MigrateCommand


@pytest.mark.unit
def test_migrate_dispatches_generic_and_command_specific_each_callbacks():
    command = MigrateCommand.__new__(MigrateCommand)
    command.journal = None
    command.execution_engine = MagicMock()
    command.log = MagicMock()
    command._execute_callbacks = MagicMock()
    migration = SimpleNamespace(
        script_name="V1__init.sql",
        version="1",
        description="init",
        type=SimpleNamespace(value="SQL"),
        checksum=123,
    )
    result = MigrateResult()

    assert command._execute_single_migration(
        migration=migration,
        scripts_dir=Path("migrations"),
        use_recursive=True,
        use_additional_dirs=None,
        dir_recursive_map=None,
        result=result,
    )

    events = [call.args[1] for call in command._execute_callbacks.call_args_list]
    assert events == ["beforeEach", "beforeEachMigrate", "afterEachMigrate", "afterEach"]
