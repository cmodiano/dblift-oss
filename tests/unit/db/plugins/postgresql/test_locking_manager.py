"""Tests for PostgreSQL migration locking behavior."""

from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from db.plugins.postgresql.postgresql.locking_manager import (
    PostgreSqlLockingManager,
    _get_advisory_lock_key,
)


class _FakeQueryExecutor:
    """Minimal query executor for native advisory lock SQL assertions."""

    def __init__(self):
        self.queries = []

    def execute_query(self, connection, sql):
        self.queries.append(sql)
        if "pg_try_advisory_lock" in sql:
            return [{"lock_acquired": True}]
        if "pg_advisory_unlock" in sql:
            return [{"lock_released": True}]
        return []

    def table_exists(self, *_args, **_kwargs):
        return False


@pytest.mark.unit
class TestPostgreSqlAdvisoryLockKey:
    def test_key_is_stable_in_current_process(self):
        assert _get_advisory_lock_key("public") == _get_advisory_lock_key("public")

    def test_key_is_schema_scoped(self):
        assert _get_advisory_lock_key("public") != _get_advisory_lock_key("tenant_a")

    def test_key_is_signed_64_bit_integer(self):
        key = _get_advisory_lock_key("public")

        assert isinstance(key, int)
        assert -(2**63) <= key <= (2**63 - 1)

    def test_key_is_stable_across_python_hash_seeds(self):
        code = (
            "from db.plugins.postgresql.postgresql.locking_manager "
            "import _get_advisory_lock_key; "
            "print(_get_advisory_lock_key('public'))"
        )

        values = []
        for seed in ("1", "2", "random"):
            env = {**os.environ, "PYTHONHASHSEED": seed}
            output = subprocess.check_output(
                [sys.executable, "-c", code],
                cwd=os.getcwd(),
                env=env,
                text=True,
                timeout=10,
            ).strip()
            values.append(output)

        assert len(set(values)) == 1

    def test_builtin_hash_would_not_be_a_valid_lock_key_source(self):
        code = "print(hash('dblift_migration_lock_public') & 0x7FFFFFFF)"

        values = []
        for seed in ("1", "2"):
            env = {**os.environ, "PYTHONHASHSEED": seed}
            output = subprocess.check_output(
                [sys.executable, "-c", code],
                cwd=os.getcwd(),
                env=env,
                text=True,
                timeout=10,
            ).strip()
            values.append(output)

        assert values[0] != values[1]


@pytest.mark.unit
class TestPostgreSqlAdvisoryLockSql:
    def test_acquire_uses_deterministic_key(self):
        executor = _FakeQueryExecutor()
        manager = PostgreSqlLockingManager(executor, log=MagicMock())

        assert manager.acquire_migration_lock(connection=object(), schema="public")

        expected_key = _get_advisory_lock_key("public")
        assert executor.queries == [f"SELECT pg_try_advisory_lock({expected_key}) as lock_acquired"]

    def test_release_uses_same_deterministic_key(self):
        executor = _FakeQueryExecutor()
        manager = PostgreSqlLockingManager(executor, log=MagicMock())

        assert manager.release_migration_lock(connection=object(), schema="public")

        expected_key = _get_advisory_lock_key("public")
        assert f"SELECT pg_advisory_unlock({expected_key}) as lock_released" in executor.queries
