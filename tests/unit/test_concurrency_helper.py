from pathlib import Path

from tests.integration.helpers import concurrency_helper
from tests.integration.helpers.cli_runner_direct import CommandResult


def test_simulate_user_sessions_uses_thread_safe_cli(monkeypatch, tmp_path: Path):
    class UnsafeDirectCLI:
        def __init__(self, config_file, migrations_dir):
            raise AssertionError("direct CLI mutates process-global argv/stdout/stderr")

    class ThreadSafeCLI:
        def __init__(self, config_file, migrations_dir):
            self.config_file = config_file
            self.migrations_dir = migrations_dir

        def migrate(self):
            return CommandResult(returncode=0, stdout="migrated", stderr="", command=[])

        def info(self):
            return CommandResult(returncode=0, stdout="info", stderr="", command=[])

    monkeypatch.setattr(concurrency_helper, "DBLiftCLI", UnsafeDirectCLI)
    monkeypatch.setattr(concurrency_helper, "ThreadSafeDBLiftCLI", ThreadSafeCLI, raising=False)

    results = concurrency_helper.simulate_user_sessions(
        tmp_path / "dblift.yaml",
        tmp_path / "migrations",
        actions=[
            lambda cli: cli.migrate(),
            lambda cli: cli.info(),
        ],
    )

    assert [result["success"] for result in results] == [True, True]
