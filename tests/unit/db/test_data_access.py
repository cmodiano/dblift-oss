from unittest.mock import MagicMock, patch

import pytest

from config import DbliftConfig
from core.logger import Log, OperationResult
from db.data_access import DataAccess


@pytest.fixture
def mock_config():
    config = MagicMock(spec=DbliftConfig)
    return config


@pytest.fixture
def mock_logger():
    logger = MagicMock(spec=Log)
    return logger


@pytest.fixture
def data_access(mock_config, mock_logger):
    return DataAccess(mock_config, mock_logger)


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    return provider


@patch("db.data_access.ProviderRegistry")
def test_initialize_success(mock_factory, data_access, mock_config, mock_logger, mock_provider):
    mock_factory.create_provider.return_value = mock_provider
    result = data_access.initialize()
    assert result.success
    assert data_access.provider == mock_provider


@patch("db.data_access.ProviderRegistry")
def test_initialize_failure(mock_factory, data_access, mock_config, mock_logger):
    mock_factory.create_provider.side_effect = Exception("init error")
    result = data_access.initialize()
    assert not result.success
    assert "Failed to initialize" in result.error_message


def test_create_connection_success(data_access, mock_provider):
    data_access.provider = mock_provider
    mock_provider.create_connection.return_value = "conn"
    result = data_access.create_connection()
    assert result.success
    assert result.data == "conn"


def test_create_connection_not_initialized(data_access):
    data_access.provider = None
    result = data_access.create_connection()
    assert not result.success
    assert "not initialized" in result.error_message


def test_create_connection_failure(data_access, mock_provider, mock_logger):
    data_access.provider = mock_provider
    mock_provider.create_connection.side_effect = Exception("conn error")
    data_access.log = mock_logger
    result = data_access.create_connection()
    assert not result.success
    assert "Failed to create database connection" in result.error_message
    mock_logger.error.assert_called()


def test_execute_query_success(data_access, mock_provider):
    data_access.provider = mock_provider
    mock_provider.execute_query.return_value = ["row1", "row2"]
    result = data_access.execute_query("SELECT 1")
    assert result.success
    assert result.data == ["row1", "row2"]


def test_execute_query_not_initialized(data_access):
    data_access.provider = None
    result = data_access.execute_query("SELECT 1")
    assert not result.success
    assert "not initialized" in result.error_message


def test_execute_query_failure(data_access, mock_provider, mock_logger):
    data_access.provider = mock_provider
    mock_provider.execute_query.side_effect = Exception("query error")
    data_access.log = mock_logger
    result = data_access.execute_query("SELECT 1")
    assert not result.success
    assert "Failed to execute query" in result.error_message
    mock_logger.error.assert_called()
    mock_logger.debug.assert_any_call("Query: SELECT 1")


def test_execute_statement_success(data_access, mock_provider):
    data_access.provider = mock_provider
    mock_provider.execute_statement.return_value = 1
    result = data_access.execute_statement("UPDATE t SET x=1")
    assert result.success
    assert result.data == 1


def test_execute_statement_not_initialized(data_access):
    data_access.provider = None
    result = data_access.execute_statement("UPDATE t SET x=1")
    assert not result.success
    assert "not initialized" in result.error_message


def test_execute_statement_failure(data_access, mock_provider, mock_logger):
    data_access.provider = mock_provider
    mock_provider.execute_statement.side_effect = Exception("stmt error")
    data_access.log = mock_logger
    result = data_access.execute_statement("UPDATE t SET x=1")
    assert not result.success
    assert "Failed to execute statement" in result.error_message
    mock_logger.error.assert_called()
    mock_logger.debug.assert_any_call("Statement: UPDATE t SET x=1")


def test_execute_statement_dict_params_error(data_access, mock_provider):
    data_access.provider = mock_provider
    result = data_access.execute_statement("UPDATE t SET x=1", params={"x": 1})
    assert not result.success
    assert "Dict parameters are not supported" in result.error_message


def test_create_schema_success(data_access, mock_provider):
    data_access.provider = mock_provider
    mock_provider.create_schema_if_not_exists.return_value = None
    result = data_access.create_schema("myschema")
    assert result.success


def test_create_schema_not_initialized(data_access):
    data_access.provider = None
    result = data_access.create_schema("myschema")
    assert not result.success
    assert "not initialized" in result.error_message


def test_create_schema_failure(data_access, mock_provider, mock_logger):
    data_access.provider = mock_provider
    mock_provider.create_schema_if_not_exists.side_effect = Exception("schema error")
    data_access.log = mock_logger
    result = data_access.create_schema("myschema")
    assert not result.success
    assert "Failed to create schema" in result.error_message
    mock_logger.error.assert_called()


def test_create_history_table_success(data_access, mock_provider):
    data_access.provider = mock_provider
    mock_provider.create_history_table_if_not_exists.return_value = None
    result = data_access.create_history_table("myschema")
    assert result.success


def test_create_history_table_not_initialized(data_access):
    data_access.provider = None
    result = data_access.create_history_table("myschema")
    assert not result.success
    assert "not initialized" in result.error_message


def test_create_history_table_failure(data_access, mock_provider, mock_logger):
    data_access.provider = mock_provider
    mock_provider.create_history_table_if_not_exists.side_effect = Exception("history error")
    data_access.log = mock_logger
    result = data_access.create_history_table("myschema")
    assert not result.success
    assert "Failed to create history table" in result.error_message
    mock_logger.error.assert_called()


def test_set_current_schema_success(data_access, mock_provider):
    data_access.provider = mock_provider
    mock_provider.set_current_schema.return_value = None
    result = data_access.set_current_schema("myschema")
    assert result.success


def test_set_current_schema_not_initialized(data_access):
    data_access.provider = None
    result = data_access.set_current_schema("myschema")
    assert not result.success
    assert "not initialized" in result.error_message


def test_set_current_schema_failure(data_access, mock_provider, mock_logger):
    data_access.provider = mock_provider
    mock_provider.set_current_schema.side_effect = Exception("schema error")
    data_access.log = mock_logger
    result = data_access.set_current_schema("myschema")
    assert not result.success
    assert "Failed to set current schema" in result.error_message
    mock_logger.error.assert_called()


def test_create_migration_lock_table_success(data_access, mock_provider):
    data_access.provider = mock_provider
    mock_provider.create_migration_lock_table_if_not_exists.return_value = None
    result = data_access.create_migration_lock_table("myschema")
    assert result.success


def test_create_migration_lock_table_not_initialized(data_access):
    data_access.provider = None
    result = data_access.create_migration_lock_table("myschema")
    assert not result.success
    assert "not initialized" in result.error_message


def test_create_migration_lock_table_failure(data_access, mock_provider, mock_logger):
    data_access.provider = mock_provider
    mock_provider.create_migration_lock_table_if_not_exists.side_effect = Exception("lock error")
    data_access.log = mock_logger
    result = data_access.create_migration_lock_table("myschema")
    assert not result.success
    assert "Failed to create migration lock table" in result.error_message
    mock_logger.error.assert_called()


def test_acquire_migration_lock_success(data_access, mock_provider):
    data_access.provider = mock_provider
    mock_provider.acquire_migration_lock.return_value = True
    result = data_access.acquire_migration_lock("myschema")
    assert result.success


def test_acquire_migration_lock_not_initialized(data_access):
    data_access.provider = None
    result = data_access.acquire_migration_lock("myschema")
    assert not result.success
    assert "not initialized" in result.error_message


def test_acquire_migration_lock_failure(data_access, mock_provider, mock_logger):
    data_access.provider = mock_provider
    mock_provider.acquire_migration_lock.side_effect = Exception("lock error")
    data_access.log = mock_logger
    result = data_access.acquire_migration_lock("myschema")
    assert not result.success
    assert "Error acquiring migration lock" in result.error_message
    mock_logger.error.assert_called()


def test_release_migration_lock_success(data_access, mock_provider):
    data_access.provider = mock_provider
    mock_provider.release_migration_lock.return_value = True
    result = data_access.release_migration_lock("myschema")
    assert result.success


def test_release_migration_lock_not_initialized(data_access):
    data_access.provider = None
    result = data_access.release_migration_lock("myschema")
    assert not result.success
    assert "not initialized" in result.error_message


def test_release_migration_lock_failure(data_access, mock_provider, mock_logger):
    data_access.provider = mock_provider
    mock_provider.release_migration_lock.side_effect = Exception("release error")
    data_access.log = mock_logger
    result = data_access.release_migration_lock("myschema")
    assert not result.success
    assert "Error releasing migration lock" in result.error_message
    mock_logger.error.assert_called()
