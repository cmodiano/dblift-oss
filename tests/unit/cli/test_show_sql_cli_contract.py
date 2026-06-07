"""End-to-end CLI text contract for ``--show-sql`` on migrate and undo."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import List, Tuple

import pytest
import yaml

DBLIFT_ROOT = Path(__file__).resolve().parents[3]


def _make_sqlite_env(tmp_path: Path) -> Tuple[Path, Path]:
    db_file = tmp_path / "test.sqlite"
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()

    config = tmp_path / "dblift.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "database": {"type": "sqlite", "path": str(db_file)},
                "migrations": {"directory": str(migrations_dir)},
            }
        )
    )
    (migrations_dir / "V1__init.sql").write_text("""
        -- ignored by show-sql because comments are not executable statements
        CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO widgets (name) VALUES ('first');
        """.strip())
    (migrations_dir / "U1__init.sql").write_text("DROP TABLE widgets;")
    return config, migrations_dir


def _cli_with_stub_license(tmp_path: Path, *args: str) -> List[str]:
    runner = tmp_path / "_run_cli.py"
    runner.write_text(
        textwrap.dedent("""
            from cli.main import main

            main()
            """),
        encoding="utf-8",
    )
    return [sys.executable, str(runner), *args]


def _run(tmp_path: Path, argv: List[str]) -> Tuple[int, str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(DBLIFT_ROOT)
    result = subprocess.run(
        _cli_with_stub_license(tmp_path, *argv),
        cwd=DBLIFT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


@pytest.mark.unit
def test_migrate_hides_sql_without_show_sql(tmp_path: Path):
    config, _ = _make_sqlite_env(tmp_path)

    exit_code, stdout, stderr = _run(
        tmp_path,
        ["--config", str(config), "migrate", "--dry-run"],
    )

    assert exit_code == 0, f"migrate --dry-run failed: stderr={stderr}"
    output = stdout + stderr
    assert "SQL Statements:" not in output
    assert "CREATE TABLE widgets" not in output
    assert "INSERT INTO widgets" not in output


@pytest.mark.unit
def test_migrate_show_sql_lists_versioned_script_statements(tmp_path: Path):
    config, _ = _make_sqlite_env(tmp_path)

    exit_code, stdout, stderr = _run(
        tmp_path,
        ["--config", str(config), "migrate", "--dry-run", "--show-sql"],
    )

    assert exit_code == 0, f"migrate --dry-run --show-sql failed: stderr={stderr}"
    output = stdout + stderr
    assert "SQL Statements:" in output
    assert "-- V1__init.sql" in output
    assert "CREATE TABLE widgets (id INTEGER PRIMARY KEY, name TEXT)" in output
    assert "INSERT INTO widgets (name) VALUES ('first')" in output


@pytest.mark.unit
def test_undo_show_sql_lists_matching_undo_script_statements(tmp_path: Path):
    config, _ = _make_sqlite_env(tmp_path)

    migrate_exit, _, migrate_stderr = _run(tmp_path, ["--config", str(config), "migrate"])
    assert migrate_exit == 0, f"setup migrate failed: stderr={migrate_stderr}"

    exit_code, stdout, stderr = _run(
        tmp_path,
        ["--config", str(config), "undo", "--dry-run", "--show-sql"],
    )

    assert exit_code == 0, f"undo --dry-run --show-sql failed: stderr={stderr}"
    output = stdout + stderr
    assert "SQL Statements:" in output
    assert "-- U1__init.sql" in output
    assert "DROP TABLE widgets" in output
    assert "CREATE TABLE widgets" not in output
