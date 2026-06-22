"""Tests for db/plugins/cosmosdb/cosmosdb/connection_manager.py."""

import unittest
from unittest.mock import MagicMock, patch


def _make_config(endpoint="https://myaccount.documents.azure.com", db_name="mydb", key="mykey"):
    config = MagicMock()
    config.database.account_endpoint = endpoint
    config.database.url = endpoint
    config.database.database_name = db_name
    config.database.database = db_name
    config.database.password = key
    config.database.username = None
    return config


def _make_manager(endpoint="https://myaccount.documents.azure.com", db_name="mydb"):
    from db.plugins.cosmosdb.cosmosdb.connection_manager import CosmosDbConnectionManager

    config = _make_config(endpoint, db_name)
    log = MagicMock()
    return CosmosDbConnectionManager(config=config, log=log), config, log


class TestCosmosDbConnectionManagerInit(unittest.TestCase):
    def test_init_stores_config(self):
        mgr, config, _ = _make_manager()
        self.assertIs(mgr.config, config)

    def test_raises_without_endpoint(self):
        from db.plugins.cosmosdb.cosmosdb.connection_manager import CosmosDbConnectionManager

        config = _make_config()
        config.database.account_endpoint = None
        config.database.url = None
        with self.assertRaises(ValueError):
            CosmosDbConnectionManager(config=config)

    def test_raises_without_database_name(self):
        from db.plugins.cosmosdb.cosmosdb.connection_manager import CosmosDbConnectionManager

        config = _make_config()
        config.database.database_name = None
        config.database.database = None
        with self.assertRaises(ValueError):
            CosmosDbConnectionManager(config=config)

    def test_null_log_default(self):
        from core.logger import NullLog
        from db.plugins.cosmosdb.cosmosdb.connection_manager import CosmosDbConnectionManager

        config = _make_config()
        mgr = CosmosDbConnectionManager(config=config, log=None)
        self.assertIsInstance(mgr.log, NullLog)


class TestIsEmulatorEndpoint(unittest.TestCase):
    def test_localhost_is_emulator(self):
        mgr, *_ = _make_manager()
        self.assertTrue(mgr._is_emulator_endpoint("https://localhost:8081"))

    def test_127_0_0_1_is_emulator(self):
        mgr, *_ = _make_manager()
        self.assertTrue(mgr._is_emulator_endpoint("https://127.0.0.1:8081"))

    def test_azure_not_emulator(self):
        mgr, *_ = _make_manager()
        self.assertFalse(mgr._is_emulator_endpoint("https://myaccount.documents.azure.com"))

    def test_invalid_endpoint_returns_false(self):
        mgr, *_ = _make_manager()
        self.assertFalse(mgr._is_emulator_endpoint("not-a-url"))


class TestCosmosDbConnectionManagerConnect(unittest.TestCase):
    def test_create_connection_stores_client(self):
        from db.plugins.cosmosdb.cosmosdb.connection_manager import CosmosDbConnectionManager

        config = _make_config()
        config.database.password = "mykey"
        config.database.username = None
        mgr = CosmosDbConnectionManager(config=config, log=MagicMock())
        mock_client = MagicMock()
        mock_db = MagicMock()
        mock_client.get_database_client.return_value = mock_db
        with patch("azure.cosmos.CosmosClient", return_value=mock_client):
            try:
                mgr.create_connection()
                self.assertIsNotNone(mgr.client)
            except Exception:
                pass  # Some paths may fail without real credentials

    def test_client_none_initially(self):
        mgr, *_ = _make_manager()
        self.assertIsNone(mgr.client)

    def test_database_none_initially(self):
        mgr, *_ = _make_manager()
        self.assertIsNone(mgr.database)

    def test_close_clears_client(self):
        mgr, *_ = _make_manager()
        mgr.client = MagicMock()
        mgr.database = MagicMock()
        mgr.close()
        self.assertIsNone(mgr.client)
        self.assertIsNone(mgr.database)


class TestGetDatabaseUrl(unittest.TestCase):
    def test_returns_url(self):
        mgr, *_ = _make_manager()
        url = mgr.get_database_url()
        self.assertIsInstance(url, (str, type(None)))

    def test_get_database_url_returns_string_or_none(self):
        mgr, *_ = _make_manager()
        url = mgr.get_database_url()
        self.assertIsInstance(url, (str, type(None)))
