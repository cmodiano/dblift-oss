from unittest.mock import MagicMock

from tests.integration.helpers.database_helper import DatabaseHelper


def test_execute_query_sets_configured_schema_before_querying():
    helper = DatabaseHelper(
        {
            "type": "postgresql",
            "schema": "TEST_SCHEMA",
        }
    )
    provider = MagicMock()
    provider.execute_query.return_value = [{"status": "completed"}]
    helper._provider = provider

    rows = helper.execute_query("SELECT status FROM migration_results")

    provider.set_current_schema.assert_called_once_with("TEST_SCHEMA")
    provider.execute_query.assert_called_once_with("SELECT status FROM migration_results", None)
    assert rows == [{"status": "completed"}]
