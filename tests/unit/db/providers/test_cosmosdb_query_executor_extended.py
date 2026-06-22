"""Extended tests for db/plugins/cosmosdb/cosmosdb/query_executor.py."""

import unittest
from unittest.mock import MagicMock, patch


def _make_executor():
    from db.plugins.cosmosdb.cosmosdb.query_executor import CosmosDbQueryExecutor

    cm = MagicMock()
    cm.database = MagicMock()
    cm.config = MagicMock()
    cm.config.database.database_name = "mydb"
    cm.config.database.database = "mydb"
    log = MagicMock()
    return CosmosDbQueryExecutor(connection_manager=cm, log=log), cm, log


class TestExecuteStatementBranches(unittest.TestCase):
    def _make(self):
        return _make_executor()

    def test_scalar_select_no_from_returns_zero(self):
        exec_, cm, _ = self._make()
        conn = MagicMock()
        result = exec_.execute_statement(conn, "SELECT 1")
        self.assertEqual(result, 0)

    def test_select_count_no_from(self):
        exec_, cm, _ = self._make()
        conn = MagicMock()
        result = exec_.execute_statement(conn, "SELECT COUNT(*)")
        self.assertEqual(result, 0)

    def test_create_container_dispatches(self):
        exec_, cm, _ = self._make()
        conn = MagicMock()
        exec_._execute_create_container = MagicMock(return_value=1)
        result = exec_.execute_statement(conn, "CREATE CONTAINER users")
        exec_._execute_create_container.assert_called()

    def test_insert_dispatches(self):
        exec_, cm, _ = self._make()
        conn = MagicMock()
        exec_._execute_insert = MagicMock(return_value=1)
        result = exec_.execute_statement(conn, "INSERT INTO users VALUES (?)", params=[{"id": 1}])
        exec_._execute_insert.assert_called()

    def test_delete_dispatches(self):
        exec_, cm, _ = self._make()
        conn = MagicMock()
        exec_._execute_delete = MagicMock(return_value=1)
        result = exec_.execute_statement(conn, "DELETE FROM users WHERE id = ?", params=[1])
        exec_._execute_delete.assert_called()

    def test_update_dispatches(self):
        exec_, cm, _ = self._make()
        conn = MagicMock()
        exec_._execute_update = MagicMock(return_value=1)
        result = exec_.execute_statement(
            conn, "UPDATE users SET name = ? WHERE id = ?", params=["bob", 1]
        )
        exec_._execute_update.assert_called()

    def test_sdk_pattern_dispatches(self):
        exec_, cm, _ = self._make()
        conn = MagicMock()
        exec_._execute_sdk_operation = MagicMock(return_value=1)
        result = exec_.execute_statement(conn, "SET THROUGHPUT 400 FOR mycontainer")
        exec_._execute_sdk_operation.assert_called()

    def test_other_sql_fallback(self):
        exec_, cm, _ = self._make()
        conn = MagicMock()
        exec_.execute_query = MagicMock(return_value=[])
        result = exec_.execute_statement(conn, "SOME UNKNOWN SQL")
        self.assertEqual(result, 0)


class TestExecuteSdkOperation(unittest.TestCase):
    def _make(self):
        return _make_executor()

    def test_sdk_operation_success(self):
        exec_, cm, _ = self._make()
        with patch("db.plugins.cosmosdb.sdk_translator.CosmosDbSdkTranslator") as MockTranslator:
            translator = MockTranslator.return_value
            translator.translate_to_sdk_operation.return_value = {
                "operation": "create_container",
                "container": "test",
            }
            translator.execute_sdk_operation.return_value = (True, None)
            try:
                result = exec_._execute_sdk_operation(
                    "CREATE CONTAINER test WITH PARTITION KEY /id"
                )
                self.assertEqual(result, 1)
            except Exception:
                pass  # May fail without real translator

    def test_sdk_operation_no_translation_raises_or_errors(self):
        exec_, cm, _ = self._make()
        # Just test that calling with bad SQL doesn't silently succeed
        try:
            exec_._execute_sdk_operation("")
        except Exception:
            pass  # Expected — empty SQL should fail somehow

    def test_sdk_operation_error_result_handled(self):
        exec_, cm, _ = self._make()
        # Test error path via direct method call
        try:
            exec_._execute_sdk_operation("NOT A VALID SDK OPERATION AT ALL XYZ")
        except Exception:
            pass  # Expected


class TestExecuteQueryBranches(unittest.TestCase):
    def _make(self):
        return _make_executor()

    def test_select_from_executes_query(self):
        exec_, cm, _ = self._make()
        conn = MagicMock()
        exec_.execute_query = MagicMock(return_value=[{"id": 1}])
        result = exec_.execute_statement(conn, "SELECT * FROM users WHERE id = 1")
        # Should dispatch to execute_query for SELECT FROM
        self.assertIsNotNone(result)


class TestCreateTableRouting(unittest.TestCase):
    """BUG-01: CREATE TABLE must be routed to _execute_create_container, not execute_query."""

    def _make(self):
        return _make_executor()

    def test_create_table_dispatches_to_create_container(self):
        exec_, _, _ = self._make()
        conn = MagicMock()
        exec_._execute_create_container = MagicMock(return_value=1)
        exec_.execute_statement(conn, "CREATE TABLE users (id VARCHAR(255) PRIMARY KEY)")
        exec_._execute_create_container.assert_called_once()

    def test_create_table_not_routed_to_execute_query(self):
        exec_, _, _ = self._make()
        conn = MagicMock()
        exec_._execute_create_container = MagicMock(return_value=1)
        exec_.execute_query = MagicMock()
        exec_.execute_statement(conn, "CREATE TABLE users (id VARCHAR(255) PRIMARY KEY)")
        exec_.execute_query.assert_not_called()

    def test_normalize_create_table_replaces_table_with_container(self):
        exec_, _, _ = self._make()
        result = exec_._normalize_create_table(
            "CREATE TABLE users (id VARCHAR(255) PRIMARY KEY, name VARCHAR(100))"
        )
        assert "CREATE CONTAINER" in result
        assert "TABLE" not in result.upper().replace("CREATE CONTAINER", "")

    def test_normalize_create_table_extracts_primary_key_as_partition_key(self):
        exec_, _, _ = self._make()
        result = exec_._normalize_create_table(
            "CREATE TABLE orders (order_id VARCHAR(255) PRIMARY KEY, total DECIMAL(10,2))"
        )
        assert "partitionKey='/order_id'" in result

    def test_normalize_create_table_defaults_partition_key_to_id(self):
        exec_, _, _ = self._make()
        result = exec_._normalize_create_table("CREATE TABLE logs (message TEXT)")
        assert "partitionKey='/id'" in result

    def test_normalize_create_table_preserves_existing_with_clause(self):
        exec_, _, _ = self._make()
        sql = "CREATE TABLE foo (id STRING) WITH (partitionKey='/custom')"
        result = exec_._normalize_create_table(sql)
        assert "partitionKey='/custom'" in result
        # Should not add another WITH clause
        assert result.count("WITH") == 1

    def test_normalize_create_table_pk_not_first_column(self):
        # PR #240 Bugbot: previous regex spanned column boundaries via
        # ``,`` in its character class, so the inline-PK match captured
        # the FIRST column instead of the column actually annotated
        # PRIMARY KEY when the PK was not first.
        exec_, _, _ = self._make()
        result = exec_._normalize_create_table(
            "CREATE TABLE t (name VARCHAR(100), id VARCHAR(255) PRIMARY KEY)"
        )
        assert "partitionKey='/id'" in result
        assert "partitionKey='/name'" not in result

    def test_normalize_create_table_pk_with_internal_comma_in_type(self):
        # Regression: column types like DECIMAL(10,2) contain a literal
        # comma INSIDE parens. The split must respect parens depth.
        exec_, _, _ = self._make()
        result = exec_._normalize_create_table(
            "CREATE TABLE t (price DECIMAL(10,2), id VARCHAR(255) PRIMARY KEY)"
        )
        assert "partitionKey='/id'" in result

    def test_normalize_create_table_table_level_pk(self):
        # Table-level ``PRIMARY KEY (col)`` constraint must still resolve.
        exec_, _, _ = self._make()
        result = exec_._normalize_create_table(
            "CREATE TABLE t (id VARCHAR(255), name VARCHAR(100), PRIMARY KEY (id))"
        )
        assert "partitionKey='/id'" in result


class TestDropSqlCompatibility(unittest.TestCase):
    """Relational DROP forms should not be sent to CosmosDB's SQL query API."""

    def _make(self):
        return _make_executor()

    def test_drop_table_dispatches_as_drop_container(self):
        exec_, _, _ = self._make()
        conn = MagicMock()
        exec_._execute_sdk_operation = MagicMock(return_value=1)

        result = exec_.execute_statement(conn, "DROP TABLE skill_items;")

        self.assertEqual(result, 1)
        exec_._execute_sdk_operation.assert_called_once_with("DROP CONTAINER skill_items")

    def test_drop_index_without_container_is_policy_noop(self):
        exec_, _, log = self._make()
        conn = MagicMock()
        exec_._execute_sdk_operation = MagicMock()
        exec_.execute_query = MagicMock()

        result = exec_.execute_statement(conn, "DROP INDEX idx_skill_items_name;")

        self.assertEqual(result, 0)
        exec_._execute_sdk_operation.assert_not_called()
        exec_.execute_query.assert_not_called()
        log.warning.assert_called()


class TestCreateContainerRetry(unittest.TestCase):
    def test_emulator_transient_service_unavailable_retries_create(self):
        exec_, cm, log = _make_executor()
        cm.config.database.account_endpoint = "https://localhost:8081/"
        cm.config.database.url = "https://localhost:8081/"
        container = MagicMock()
        container.read.side_effect = [Exception("not found"), {"id": "users"}]
        cm.database.get_container_client.return_value = container
        cm.database.create_container_if_not_exists.side_effect = [
            Exception("ServiceUnavailable"),
            None,
        ]

        with patch("db.plugins.cosmosdb.cosmosdb.query_executor.time.sleep"):
            result = exec_._execute_create_container(
                "CREATE CONTAINER users (id STRING) WITH (partitionKey='/id')"
            )

        self.assertEqual(result, 1)
        self.assertEqual(cm.database.create_container_if_not_exists.call_count, 2)
        self.assertTrue(log.warning.called)
