"""BUG-07 regression: create_schema_and_history_table retries on concurrent-create races.

When two migrate processes race, PostgreSQL's ``CREATE SCHEMA IF NOT EXISTS`` can
raise "duplicate key value violates unique constraint" on pg_namespace and leave
the losing transaction in an aborted state. Before the retry loop, that surfaced
as a hard migrate failure ("Transaction is aborted before/during executing
statement") even though no data corruption occurred.

The retry loop in ``MigrationHistoryManager.create_schema_and_history_table``
now catches the race, rolls back the aborted transaction on the provider, and
retries so the losing process converges with the winner.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.migration.history.migration_history_manager import MigrationHistoryManager


def _make_manager(provider: MagicMock) -> MigrationHistoryManager:
    return MigrationHistoryManager(
        provider=provider,
        schema="new_schema",
        installed_by="tester",
        logger=MagicMock(),
        table_name="dblift_schema_history",
    )


@pytest.mark.unit
class TestCreateSchemaAndHistoryTableRetry:
    def test_succeeds_on_first_try_when_no_race(self):
        provider = MagicMock()
        mgr = _make_manager(provider)

        mgr.create_schema_and_history_table(create_schema=True)

        provider.create_schema_if_not_exists.assert_called_once_with("new_schema")
        provider.create_history_table_if_not_exists.assert_called_once()

    def test_retries_and_recovers_from_duplicate_key_race(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        provider = MagicMock()

        # First call raises a PG unique-violation; second call succeeds.
        call_count = {"n": 0}

        def flaky_create_schema(schema):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception(
                    "ERROR: duplicate key value violates unique constraint "
                    '"pg_namespace_nspname_index"\n  Key (nspname)=(new_schema) already exists.'
                )

        provider.create_schema_if_not_exists.side_effect = flaky_create_schema

        mgr = _make_manager(provider)
        mgr.create_schema_and_history_table(create_schema=True)

        assert call_count["n"] == 2
        provider.rollback_transaction.assert_called()

    def test_retries_on_already_exists(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        provider = MagicMock()
        call_count = {"n": 0}

        def flaky(*_args, **_kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("relation 'dblift_schema_history' already exists")

        provider.create_history_table_if_not_exists.side_effect = flaky

        mgr = _make_manager(provider)
        mgr.create_schema_and_history_table()

        assert call_count["n"] == 2

    def test_retries_on_transaction_aborted_cascade(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        provider = MagicMock()
        call_count = {"n": 0}

        def flaky(*_args, **_kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise Exception("Transaction is aborted before/during executing statement")

        provider.create_history_table_if_not_exists.side_effect = flaky

        mgr = _make_manager(provider)
        mgr.create_schema_and_history_table()

        assert call_count["n"] == 2
        provider.rollback_transaction.assert_called()

    def test_gives_up_after_max_attempts_and_reraises(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        provider = MagicMock()
        provider.create_schema_if_not_exists.side_effect = Exception(
            "duplicate key value violates unique constraint"
        )

        mgr = _make_manager(provider)
        with pytest.raises(Exception, match="duplicate key"):
            mgr.create_schema_and_history_table(create_schema=True)

        assert provider.create_schema_if_not_exists.call_count == 3

    def test_non_race_error_does_not_retry(self, monkeypatch):
        monkeypatch.setattr("time.sleep", lambda *_: None)
        provider = MagicMock()
        provider.create_schema_if_not_exists.side_effect = Exception("permission denied")

        mgr = _make_manager(provider)
        with pytest.raises(Exception, match="permission denied"):
            mgr.create_schema_and_history_table(create_schema=True)

        # Permission errors are not a concurrency race — must not retry.
        assert provider.create_schema_if_not_exists.call_count == 1
