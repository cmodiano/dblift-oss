"""Tests for the configuration system."""

import os
from unittest.mock import mock_open, patch

import pytest
import yaml

from config.database_config import DatabaseConfig
from config.dblift_config import DbliftConfig

PG_URL = "postgresql+psycopg://localhost:5432/testdb"
PG_URL_CREDS = "postgresql+psycopg://myuser:mypass@localhost:5432/testdb"


@pytest.mark.unit
class TestDatabaseConfig:
    """Test suite for DatabaseConfig class."""

    def test_create_from_dict(self):
        config_dict = {
            "url": PG_URL,
            "username": "postgres",
            "password": "pw",
        }
        config = DatabaseConfig.from_dict(config_dict)
        assert config.type == "postgresql"
        assert config.url == PG_URL
        assert config.username == "postgres"
        assert config.password == "pw"

    def test_create_from_url(self):
        config = DatabaseConfig.from_url(PG_URL_CREDS)
        assert config.type == "postgresql"
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.username == "myuser"
        assert config.password == "mypass"

    def test_create_from_url_with_credentials(self):
        config = DatabaseConfig.from_url(PG_URL_CREDS)
        assert config.type == "postgresql"
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.username == "myuser"
        assert config.password == "mypass"

    def test_create_from_url_with_properties(self):
        url = "postgresql+psycopg://myuser:mypass@localhost:5432/testdb?sslmode=require"
        config = DatabaseConfig.from_url(url)
        assert config.type == "postgresql"
        assert config.extra_params.get("sslmode") == "require"

    def test_create_from_url_postgresql(self):
        config = DatabaseConfig.from_url(PG_URL_CREDS)
        assert config.type == "postgresql"
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "testdb"

    def test_create_from_url_mysql(self):
        database_url = "mysql+pymysql://localhost:3306/mydb?useSSL=false"
        config = DatabaseConfig.from_dict(
            {"url": database_url, "username": "root", "password": "pw"}
        )
        assert config.type == "mysql"
        assert config.host == "localhost"
        assert config.port == 3306
        assert config.database == "mydb"
        assert config.extra_params["useSSL"] == "false"

    def test_create_from_url_sqlite(self):
        config = DatabaseConfig.from_dict({"url": "sqlite:///tmp/test.db"})
        assert config.type == "sqlite"

    def test_invalid_database_url(self):
        with pytest.raises(ValueError):
            DatabaseConfig.from_url("invalid_url")

    def test_missing_required_fields(self):
        config_dict = {
            "type": "postgresql",
            "host": "localhost",
            # Missing URL/port/database
        }
        with pytest.raises(ValueError):
            DatabaseConfig.from_dict(config_dict)


@pytest.mark.unit
class TestDbliftConfig:
    """Test suite for DbliftConfig class."""

    def test_create_from_file(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        file_config = {
            "database": {
                "url": PG_URL,
                "username": "postgres",
                "password": "pw",
            }
        }
        config_file.write_text(yaml.dump(file_config))
        args = {
            "db_url": PG_URL,
            "db_username": "postgres",
            "db_password": "pw",
            "config_file": str(config_file),
        }
        config = DbliftConfig.from_all_sources(args)
        assert config.database.type == "postgresql"
        assert config.database.username == "postgres"
        assert config.database.password == "pw"

    def test_create_from_env(self, monkeypatch):
        monkeypatch.setenv("DBLIFT_DB_URL", PG_URL)
        monkeypatch.setenv("DBLIFT_DB_USER", "env_user")
        monkeypatch.setenv("DBLIFT_DB_PASSWORD", "env_pw")
        config = DbliftConfig.from_dict(DbliftConfig.from_env_dict())
        assert config.database.type == "postgresql"
        assert config.database.username == "env_user"
        assert config.database.password == "env_pw"

    def test_create_from_args(self):
        args = {
            "db_url": PG_URL,
            "db_username": "args_user",
            "db_password": "args_pw",
            "config_file": None,
        }
        config = DbliftConfig.from_all_sources(args)
        assert config.database.url == PG_URL
        assert config.database.username == "args_user"
        assert config.database.password == "args_pw"

    def test_config_precedence(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        file_config = {
            "database": {
                "url": PG_URL,
                "username": "file_user",
                "password": "file_pw",
            }
        }
        config_file.write_text(yaml.dump(file_config))
        monkeypatch.setenv("DBLIFT_DB_USER", "env_user")
        monkeypatch.setenv("DBLIFT_DB_PASSWORD", "env_pw")
        args = {
            "db_url": PG_URL,
            "db_username": "args_user",
            "db_password": "args_pw",
            "config_file": str(config_file),
        }
        config = DbliftConfig.from_all_sources(args)
        assert config.database.username == "args_user"
        assert config.database.password == "args_pw"

    def test_url_precedence(self, tmp_path, monkeypatch):
        file_url = "postgresql+psycopg://localhost:5432/filedb"
        env_url = "postgresql+psycopg://localhost:5432/envdb"
        args_url = "postgresql+psycopg://localhost:5432/argsdb"

        config_file = tmp_path / "config.yaml"
        file_config = {
            "database": {
                "url": file_url,
                "username": "file_user",
                "password": "file_pw",
            }
        }
        config_file.write_text(yaml.dump(file_config))
        monkeypatch.setenv("DBLIFT_DB_URL", env_url)
        monkeypatch.setenv("DBLIFT_DB_USER", "env_user")
        monkeypatch.setenv("DBLIFT_DB_PASSWORD", "env_pw")
        args = {
            "db_url": args_url,
            "db_username": "args_user",
            "db_password": "args_pw",
            "config_file": str(config_file),
        }
        config = DbliftConfig.from_all_sources(args)
        assert config.database.url == args_url
        assert config.database.username == "args_user"

    def test_username_password_precedence_url_vs_env_vs_args(self, tmp_path, monkeypatch):
        url_with_creds = PG_URL_CREDS
        config_file = tmp_path / "config.yaml"
        file_config = {"database": {"url": url_with_creds}}
        config_file.write_text(yaml.dump(file_config))

        args = {"config_file": str(config_file)}
        config = DbliftConfig.from_all_sources(args)
        assert config.database.username == "myuser"
        assert config.database.password == "mypass"

        monkeypatch.setenv("DBLIFT_DB_USER", "env_user")
        monkeypatch.setenv("DBLIFT_DB_PASSWORD", "env_pw")
        config = DbliftConfig.from_all_sources(args)
        assert config.database.username == "env_user"
        assert config.database.password == "env_pw"

        args = {
            "db_url": url_with_creds,
            "db_username": "args_user",
            "db_password": "args_pw",
            "config_file": str(config_file),
        }
        config = DbliftConfig.from_all_sources(args)
        assert config.database.username == "args_user"
        assert config.database.password == "args_pw"

    def test_config_merging(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        file_config = {
            "database": {
                "url": PG_URL,
                "username": "file_user",
                "password": "file_pw",
            }
        }
        config_file.write_text(yaml.dump(file_config))
        args = {
            "db_url": PG_URL,
            "db_username": "merged_user",
            "db_password": "merged_pw",
            "config_file": str(config_file),
        }
        config = DbliftConfig.from_all_sources(args)
        assert config.database.username == "merged_user"
        assert config.database.password == "merged_pw"

    def test_config_merging_with_tempfile_env_args(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        file_config = {
            "database": {
                "url": PG_URL,
                "username": "file_user",
                "password": "file_pw",
            }
        }
        config_file.write_text(yaml.dump(file_config))
        monkeypatch.setenv("DBLIFT_DB_USER", "env_user")
        monkeypatch.setenv("DBLIFT_DB_PASSWORD", "env_pw")
        args = {
            "db_url": PG_URL,
            "db_username": "args_user",
            "db_password": "args_pw",
            "config_file": str(config_file),
        }
        config = DbliftConfig.from_all_sources(args)
        assert config.database.username == "args_user"
        assert config.database.password == "args_pw"

    def test_invalid_config_file(self):
        with patch("builtins.open", mock_open(read_data="invalid: yaml: content")):
            with pytest.raises(yaml.YAMLError):
                DbliftConfig.from_file("config.yaml")

    def test_missing_required_config(self):
        with pytest.raises(ValueError):
            DbliftConfig.from_dict({})

    def test_invalid_database_type(self):
        config_dict = {
            "database": {
                "type": "invalid_type",
                "host": "localhost",
                "port": 5432,
                "database": "testdb",
            }
        }
        with pytest.raises(ValueError):
            DbliftConfig.from_dict(config_dict)
