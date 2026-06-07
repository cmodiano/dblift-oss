"""Unit tests for config.config_builder module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from config.config_builder import ConfigBuilder, ConfigurationError
from config.database_config import (
    BaseDatabaseConfig,
    MySqlConfig,
    OracleConfig,
    PostgreSqlConfig,
    SqlServerConfig,
)
from config.dblift_config import DbliftConfig


@pytest.mark.unit
class TestConfigurationError:
    """Test ConfigurationError exception."""

    def test_configuration_error(self):
        """Test ConfigurationError can be raised."""
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("Test error")


@pytest.mark.unit
class TestConfigBuilder:
    """Test ConfigBuilder class."""

    def test_merge_database_overrides_no_url(self):
        """Test merge_database_overrides without URL override."""
        base_config = BaseDatabaseConfig.create(
            {
                "type": "postgresql",
                "url": "postgresql+psycopg://localhost/mydb",
                "username": "user",
                "password": "pass",
                "schema": "public",
            }
        )
        overrides = {"username": "newuser", "schema": "newschema"}

        result = ConfigBuilder.merge_database_overrides(base_config, overrides)

        assert result.username == "newuser"
        assert result.schema == "newschema"
        assert result.url == base_config.url  # URL unchanged

    def test_merge_database_overrides_same_type(self):
        """Test merge_database_overrides with URL override but same database type."""
        base_config = BaseDatabaseConfig.create(
            {
                "type": "postgresql",
                "url": "postgresql+psycopg://localhost/mydb",
                "username": "user",
                "password": "pass",
                "schema": "public",
                "extra_params": {"sslmode": "require"},
            }
        )
        overrides = {"url": "postgresql+psycopg://localhost/newdb", "username": "newuser"}

        result = ConfigBuilder.merge_database_overrides(base_config, overrides)

        assert isinstance(result, PostgreSqlConfig)
        assert result.url == "postgresql+psycopg://localhost/newdb"
        assert result.username == "newuser"
        assert result.extra_params == {"sslmode": "require"}

    def test_merge_database_overrides_different_type(self):
        """Test merge_database_overrides with URL override changing database type."""
        base_config = BaseDatabaseConfig.create(
            {
                "type": "postgresql",
                "url": "postgresql+psycopg://localhost/mydb",
                "username": "user",
                "password": "pass",
                "schema": "public",
            }
        )
        overrides = {"url": "mssql+pymssql://localhost/newdb", "username": "newuser"}

        result = ConfigBuilder.merge_database_overrides(base_config, overrides)

        assert isinstance(result, SqlServerConfig)
        assert result.url == "mssql+pymssql://localhost/newdb"
        assert result.username == "newuser"

    def test_merge_oracle_url_override_replaces_service_name(self):
        base_config = BaseDatabaseConfig.create(
            {
                "type": "oracle",
                "url": "oracle+oracledb://db.example.com:1521/?service_name=OLD",
                "host": "db.example.com",
                "port": 1521,
                "service_name": "OLD",
                "username": "user",
                "password": "pass",
            }
        )

        result = ConfigBuilder.merge_database_overrides(
            base_config,
            {"url": "oracle+oracledb://db.example.com:1521/?service_name=NEW"},
        )

        assert isinstance(result, OracleConfig)
        assert result.service_name == "NEW"
        assert result.sid is None
        assert "service_name=NEW" in result.build_database_url()

    def test_merge_database_overrides_url_parsing_failure(self):
        """Test merge_database_overrides when URL parsing fails."""
        base_config = BaseDatabaseConfig.create(
            {
                "type": "postgresql",
                "url": "postgresql+psycopg://localhost/mydb",
                "username": "user",
                "password": "pass",
                "schema": "public",
            }
        )
        overrides = {"url": "invalid_url", "username": "newuser"}

        result = ConfigBuilder.merge_database_overrides(base_config, overrides)

        # Should fall back to individual overrides
        assert result.username == "newuser"
        assert result.url == "invalid_url"

    def test_merge_database_overrides_rejects_native_database_url(self):
        """legacy URL overrides fail instead of keeping the old type."""
        base_config = BaseDatabaseConfig.create(
            {
                "type": "sqlserver",
                "url": "mssql+pymssql://localhost/mydb",
                "username": "user",
                "password": "pass",
            }
        )
        overrides = {"url": "jdbc:mysql://localhost/newdb", "username": "newuser"}

        with pytest.raises(ValueError, match="Legacy database URLs are no longer supported"):
            ConfigBuilder.merge_database_overrides(base_config, overrides)

    def test_merge_database_overrides_config_creation_failure(self):
        """Test merge_database_overrides when config creation fails."""
        base_config = BaseDatabaseConfig.create(
            {
                "type": "postgresql",
                "url": "postgresql+psycopg://localhost/mydb",
                "username": "user",
                "password": "pass",
                "schema": "public",
            }
        )
        overrides = {
            "url": "oracle+oracledb://localhost:1521?service_name=XE",
            "username": "newuser",
        }

        with patch(
            "config.config_builder.BaseDatabaseConfig.create", side_effect=ValueError("Error")
        ):
            with pytest.raises(ValueError, match="Error"):
                ConfigBuilder.merge_database_overrides(base_config, overrides)

    def test_build_from_dict_success(self):
        """Test build_from_dict with valid dictionary."""
        config_dict = {
            "type": "postgresql",
            "url": "postgresql+psycopg://localhost/mydb",
            "username": "user",
            "password": "pass",
            "schema": "public",
        }

        result = ConfigBuilder.build_from_dict(config_dict)

        assert isinstance(result, PostgreSqlConfig)
        assert result.url == "postgresql+psycopg://localhost/mydb"
        assert result.username == "user"

    def test_build_from_dict_missing_type(self):
        """Test build_from_dict with missing type."""
        config_dict = {"url": "postgresql+psycopg://localhost/mydb"}

        with pytest.raises(ConfigurationError, match="Database type is required"):
            ConfigBuilder.build_from_dict(config_dict)

    def test_build_from_dict_creation_failure(self):
        """Test build_from_dict when config creation fails."""
        config_dict = {"type": "invalid_type", "url": "jdbc:invalid://localhost"}

        with patch(
            "config.config_builder.BaseDatabaseConfig.create",
            side_effect=ValueError("Invalid type"),
        ):
            with pytest.raises(ConfigurationError):
                ConfigBuilder.build_from_dict(config_dict)

    def test_validate_required_fields_success(self):
        """Test validate_required_fields with valid config."""
        config = BaseDatabaseConfig.create(
            {
                "type": "postgresql",
                "url": "postgresql+psycopg://localhost/mydb?user=testuser&password=testpass",
                "username": "testuser",
                "password": "testpass",
                "schema": "public",
            }
        )

        # Should not raise
        ConfigBuilder.validate_required_fields(config)

    def test_validate_required_fields_missing_url(self):
        """Test validate_required_fields with missing URL."""
        # Create config with empty URL - BaseDatabaseConfig.create may validate, so use replace
        base_config = BaseDatabaseConfig.create(
            {
                "type": "postgresql",
                "url": "postgresql+psycopg://localhost/mydb",
                "username": "user",
                "password": "pass",
                "schema": "public",
            }
        )
        from dataclasses import replace

        config = replace(base_config, url="")

        with pytest.raises(ConfigurationError, match="Database URL is required"):
            ConfigBuilder.validate_required_fields(config)

    def test_validate_required_fields_missing_username(self):
        """Test validate_required_fields with missing username."""
        base_config = BaseDatabaseConfig.create(
            {
                "type": "postgresql",
                "url": "postgresql+psycopg://localhost/mydb",
                "username": "user",
                "password": "pass",
                "schema": "public",
            }
        )
        from dataclasses import replace

        config = replace(base_config, username=None)

        with pytest.raises(ConfigurationError, match="Database username is required"):
            ConfigBuilder.validate_required_fields(config)

    def test_validate_required_fields_username_in_url(self):
        """Test validate_required_fields with username in URL."""
        # Use URL with credentials embedded (Oracle format)
        config = BaseDatabaseConfig.create(
            {
                "type": "oracle",
                "url": "oracle+oracledb://testuser:testpass@localhost:1521?service_name=mydb",
                "schema": "public",
            }
        )

        # Should not raise - username is in URL
        ConfigBuilder.validate_required_fields(config)

    def test_validate_required_fields_missing_password(self):
        """Test validate_required_fields with missing password."""
        base_config = BaseDatabaseConfig.create(
            {
                "type": "postgresql",
                "url": "postgresql+psycopg://localhost/mydb",
                "username": "user",
                "password": "pass",
                "schema": "public",
            }
        )
        from dataclasses import replace

        config = replace(base_config, password=None)

        with pytest.raises(ConfigurationError, match="Database password is required"):
            ConfigBuilder.validate_required_fields(config)

    def test_validate_required_fields_password_in_url(self):
        """Test validate_required_fields with password in URL."""
        # Use URL with credentials embedded (Oracle format)
        config = BaseDatabaseConfig.create(
            {
                "type": "oracle",
                "url": "oracle+oracledb://testuser:testpass@localhost:1521?service_name=mydb",
                "username": None,
                "password": None,
                "schema": "public",
            }
        )

        # Should not raise - password is in URL
        ConfigBuilder.validate_required_fields(config)

    def test_validate_required_fields_missing_schema_uses_postgresql_default(self):
        """Test validate_required_fields derives a plugin default schema."""
        config = BaseDatabaseConfig.create(
            {
                "type": "postgresql",
                "url": "postgresql+psycopg://localhost/mydb?user=testuser&password=testpass",
                "username": "testuser",
                "password": "testpass",
                "schema": None,
            }
        )

        ConfigBuilder.validate_required_fields(config)

        assert config.schema == "public"

    def test_validate_required_fields_missing_mysql_schema_uses_database_catalog(self):
        """Test validate_required_fields derives MySQL schema from the database catalog."""
        config = BaseDatabaseConfig.create(
            {
                "type": "mysql",
                "url": "mysql+pymysql://localhost/mydb?user=testuser&password=testpass",
                "username": "testuser",
                "password": "testpass",
                "schema": None,
            }
        )

        ConfigBuilder.validate_required_fields(config)

        assert config.schema == "mydb"

    def test_build_default(self):
        """Test build with no arguments."""
        with pytest.raises(ConfigurationError, match="No configuration source provided"):
            ConfigBuilder.build()

    def test_build_with_file_path_exists(self):
        """Test build with existing file path merges YAML dict before construction."""
        with patch("config.config_builder.Path.exists", return_value=True):
            with patch.object(
                DbliftConfig,
                "load_config_data_from_yaml",
                return_value={
                    "database": {
                        "type": "postgresql",
                        "url": "postgresql+psycopg://localhost/db",
                        "username": "user",
                        "password": "pass",
                    },
                    "logging": {"level": "ERROR"},
                },
            ):
                result = ConfigBuilder.build(file_path="test.yaml", env_overrides=False)

        assert result is not None
        assert result.logging.level == "ERROR"

    def test_build_file_without_database_raises(self, tmp_path):
        """YAML without database is incomplete when no default config exists."""
        yaml_file = tmp_path / "partial.yaml"
        yaml_file.write_text(
            "logging:\n  level: CRITICAL\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigurationError, match="Database configuration is required"):
            ConfigBuilder.build(file_path=yaml_file, env_overrides=False)

    def test_build_with_file_path_not_exists(self):
        """Build with a non-existent file path raises FileNotFoundError (matches CLI behaviour)."""
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            ConfigBuilder.build(file_path="nonexistent.yaml")

    def test_build_with_file_load_failure(self):
        """Test build when file load fails."""
        with patch("config.config_builder.Path.exists", return_value=True):
            with patch(
                "config.dblift_config.DbliftConfig.load_config_data_from_yaml",
                side_effect=Exception("Error"),
            ):
                with pytest.warns(UserWarning, match="Failed to load config file"):
                    with pytest.raises(
                        ConfigurationError, match="No configuration source provided"
                    ):
                        ConfigBuilder.build(file_path="test.yaml")

    def test_build_with_env_overrides(self):
        """Test build with env_overrides=True merges env dict when DBLIFT_DB_* vars are set."""
        with patch(
            "config.config_builder.DbliftConfig.from_env_dict",
            return_value={
                "database": {
                    "type": "postgresql",
                    "url": "postgresql+psycopg://localhost/test",
                    "username": "env_user",
                    "password": "env_pass",
                }
            },
        ):
            result = ConfigBuilder.build(env_overrides=True)

            assert result is not None
            assert result.database.url == "postgresql+psycopg://localhost/test"
            assert result.database.username == "env_user"

    def test_build_with_env_overrides_false(self):
        """Test build with env_overrides=False."""
        with pytest.raises(ConfigurationError, match="No configuration source provided"):
            ConfigBuilder.build(env_overrides=False)

    def test_build_with_kwargs_database_url(self):
        """Test build with database_url kwargs."""
        result = ConfigBuilder.build(
            database_url="postgresql+psycopg://user:pass@localhost/mydb",
            database_schema="public",
        )

        assert result.database.type == "postgresql"
        assert result.database.schema == "public"

    def test_build_with_kwargs_db_url(self):
        """Test build with db_url kwargs."""
        result = ConfigBuilder.build(
            db_url="postgresql+psycopg://user:pass@localhost/mydb", database_schema="public"
        )

        assert result.database.type == "postgresql"

    def test_build_with_kwargs_database_username(self):
        """Test build with database_username kwargs."""
        result = ConfigBuilder.build(
            database_url="postgresql+psycopg://localhost/mydb",
            database_username="testuser",
            database_password="testpass",
            database_schema="public",
        )

        assert result.database.username == "testuser"

    def test_build_with_kwargs_database_password(self):
        """Test build with database_password kwargs."""
        result = ConfigBuilder.build(
            database_url="postgresql+psycopg://user@localhost/mydb",
            database_password="testpass",
            database_schema="public",
        )

        assert result.database.password == "testpass"

    def test_build_with_kwargs_database_schema(self):
        """Test build with database_schema kwargs."""
        result = ConfigBuilder.build(
            database_url="postgresql+psycopg://user:pass@localhost/mydb",
            database_schema="public",
        )

        assert result.database.schema == "public"

    def test_build_with_kwargs_log_level(self):
        """Test build with log_level kwargs."""
        result = ConfigBuilder.build(
            database_url="postgresql+psycopg://user:pass@localhost/mydb",
            database_schema="public",
            log_level="DEBUG",
        )

        assert result.log_level == "DEBUG"

    def test_build_with_kwargs_history_table(self):
        """Test build with history_table kwargs."""
        result = ConfigBuilder.build(
            database_url="postgresql+psycopg://user:pass@localhost/mydb",
            database_schema="public",
            history_table="custom_history",
        )

        assert result.history_table == "custom_history"

    def test_from_file_with_path(self):
        """Test from_file with explicit path."""
        with patch("config.config_builder.DbliftConfig.from_file") as mock_from_file:
            mock_config = Mock()
            mock_from_file.return_value = mock_config

            result = ConfigBuilder.from_file("test.yaml")

            assert result == mock_config
            mock_from_file.assert_called_once_with("test.yaml")

    def test_from_file_default_paths(self):
        """Test from_file with None path (uses defaults)."""
        with patch("config.config_builder.Path.exists") as mock_exists:
            mock_exists.return_value = True
            with patch("config.config_builder.DbliftConfig.from_file") as mock_from_file:
                mock_config = Mock()
                mock_from_file.return_value = mock_config

                result = ConfigBuilder.from_file(None)

                assert result == mock_config

    def test_from_file_no_defaults(self):
        """Test from_file when no default files exist."""
        with patch("config.config_builder.Path.exists", return_value=False):
            with pytest.raises(ConfigurationError, match="No configuration file found"):
                ConfigBuilder.from_file(None)

    def test_from_dict(self):
        """Test from_dict."""
        config_dict = {
            "database": {
                "url": "postgresql+psycopg://localhost/mydb",
                "username": "user",
                "password": "pass",
                "schema": "public",
            }
        }

        with patch("config.config_builder.DbliftConfig.from_dict") as mock_from_dict:
            mock_config = Mock()
            mock_from_dict.return_value = mock_config

            result = ConfigBuilder.from_dict(config_dict)

            assert result == mock_config
            mock_from_dict.assert_called_once_with(config_dict)

    def test_from_env_with_database_config(self):
        """Test from_env with database config in environment."""
        env_dict = {
            "database": {
                "url": "postgresql+psycopg://localhost/mydb",
                "username": "user",
                "password": "pass",
                "schema": "public",
            }
        }

        with patch("config.config_builder.DbliftConfig.from_env_dict", return_value=env_dict):
            with patch("config.config_builder.DbliftConfig.from_dict") as mock_from_dict:
                mock_config = Mock()
                mock_from_dict.return_value = mock_config

                result = ConfigBuilder.from_env()

                assert result == mock_config
                mock_from_dict.assert_called_once_with(env_dict)

    def test_from_env_no_database_config(self):
        """Test from_env without database config."""
        with patch("config.config_builder.DbliftConfig.from_env_dict", return_value={}):
            with pytest.raises(ConfigurationError, match="No environment configuration found"):
                ConfigBuilder.from_env()

    def test_from_env_no_url(self):
        """Test from_env with config but no URL."""
        env_dict = {"database": {"username": "user"}}

        with patch("config.config_builder.DbliftConfig.from_env_dict", return_value=env_dict):
            with pytest.raises(ConfigurationError, match="Database type is required"):
                ConfigBuilder.from_env()

    def test_merge_no_configs(self):
        """Test merge with no configs."""
        with pytest.raises(ConfigurationError, match="At least one configuration"):
            ConfigBuilder.merge()

    def test_merge_single_config(self):
        """Test merge with single config."""
        config = Mock()
        config.to_dict.return_value = {}

        result = ConfigBuilder.merge(config)

        assert result == config

    def test_merge_multiple_configs(self):
        """Test merge with multiple configs."""
        config1 = Mock()
        config1.to_dict.return_value = {}
        config2 = Mock()
        config2.to_dict.return_value = {}
        config1.merge = Mock()

        result = ConfigBuilder.merge(config1, config2)

        assert result == config1
        config1.merge.assert_called_once()
