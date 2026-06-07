"""
Configuration builder utility for merging database configuration overrides.

This module provides utilities for safely merging database configuration
overrides, handling URL parsing, and creating new configurations when needed.
"""

import warnings
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, Optional, Union

from config.database_config import BaseDatabaseConfig, _detect_dialect_from_url
from config.dblift_config import DbliftConfig
from config.errors import ConfigurationError


class ConfigBuilder:
    """Helper class for building and merging configurations."""

    #: Keyword names interpreted by :meth:`build` from ``**kwargs`` (merged into config).
    #: Used by :func:`api._client_factory.client_from_config_file` so those keys are not
    #: forwarded again to :class:`~api.client.DBLiftClient`.
    CONFIG_BUILD_KWARG_KEYS: frozenset[str] = frozenset(
        {
            "database_url",
            "db_url",
            "database_username",
            "db_username",
            "database_password",
            "db_password",
            "database_schema",
            "db_schema",
            "database_type",
            "db_type",
            "account_endpoint",
            "account_key",
            "database",
            "database_name",
            "container_name",
            "use_managed_identity",
            "history_table",
            "snapshot_table",
            "max_snapshots",
            "log_level",
            "log_file",
            "log_dir",
            "log_format",
            "env_overrides",
        }
    )

    @staticmethod
    def merge_database_overrides(
        base_config: BaseDatabaseConfig, overrides: Dict[str, Any]
    ) -> BaseDatabaseConfig:
        """Merge database configuration overrides.

        This method handles the complex logic of merging database configuration
        overrides, including:
        - Detecting database type changes from URL
        - Creating new config objects when type changes
        - Applying individual overrides when type doesn't change

        Args:
            base_config: Base database configuration
            overrides: Dictionary of override values

        Returns:
            New database configuration with overrides applied.
            The original base_config is never modified (immutable).

        Raises:
            ConfigurationError: If configuration creation fails and fallback also fails

        Example:
            >>> base = SqlServerDatabaseConfig(url="mssql+pymssql://localhost/master")
            >>> overrides = {"url": "postgresql+psycopg://localhost/mydb", "username": "user"}
            >>> new_config = ConfigBuilder.merge_database_overrides(base, overrides)
            >>> # new_config is now a PostgreSQLDatabaseConfig
        """
        override_type = str(overrides.get("type") or "").lower()
        if override_type and override_type != str(base_config.type or "").lower():
            try:
                merged_data = base_config.to_dict()
                merged_data.update(overrides)
                return BaseDatabaseConfig.create(merged_data)
            except ValueError:
                return ConfigBuilder._apply_overrides_to_copy(base_config, overrides)

        # If URL is being overridden, infer the database type from the native URL scheme.
        if "url" in overrides:
            override_url = str(overrides["url"])
            if override_url.strip().lower().startswith("jdbc:"):
                raise ValueError(
                    "Legacy database URLs are no longer supported; use a SQLAlchemy URL"
                )
            try:
                merged_data = base_config.to_dict()
                merged_data.update(overrides)
                for derived_key in ("host", "port", "database", "service_name", "sid"):
                    if derived_key not in overrides:
                        merged_data[derived_key] = None

                detected_type = _detect_dialect_from_url(override_url)
                if detected_type:
                    merged_data["type"] = detected_type
                    return BaseDatabaseConfig.create(merged_data)

                # Apply overrides individually if type doesn't change.
                sqlite_result = ConfigBuilder._try_create_sqlite_config(overrides, base_config)
                if sqlite_result is not None:
                    return sqlite_result
                return ConfigBuilder._apply_overrides_to_copy(base_config, overrides)
            except Exception:
                detected_type = _detect_dialect_from_url(str(overrides["url"]))
                if detected_type:
                    from db.provider_registry import ProviderRegistry

                    if ProviderRegistry.is_native_dialect(detected_type):
                        raise
                # If URL parsing fails, fall back to individual overrides
                sqlite_result = ConfigBuilder._try_create_sqlite_config(overrides, base_config)
                if sqlite_result is not None:
                    return sqlite_result
                return ConfigBuilder._apply_overrides_to_copy(base_config, overrides)
        else:
            # Apply individual overrides if no URL override
            # Create a copy to avoid mutating the original
            result = replace(base_config)
            for key, value in overrides.items():
                if hasattr(result, key):
                    setattr(result, key, value)
            return result

    @staticmethod
    def _apply_overrides_to_copy(
        base_config: "BaseDatabaseConfig", overrides: Dict[str, Any]
    ) -> "BaseDatabaseConfig":
        """Shallow-copy base_config, apply all overrides, then enforce sqlite type if the URL demands it.

        The sqlite type fix is applied *after* the setattr loop so that an
        accidental ``type`` key in overrides cannot silently win over the URL.
        """
        result = replace(base_config)
        for key, value in overrides.items():
            if hasattr(result, key):
                setattr(result, key, value)
        if overrides.get("url"):
            _url_lower = overrides["url"].lower()
            if _url_lower.startswith(("sqlite:", "sqlite3:")):
                result.type = "sqlite"  # lint: allow-dialect-string: dialect dispatch
        return result

    @staticmethod
    def _try_create_sqlite_config(
        overrides: Dict[str, Any], base_config: "BaseDatabaseConfig"
    ) -> "Optional[BaseDatabaseConfig]":
        """Return a SQLiteConfig when the override URL is a sqlite:// URL, else None.

        Mutating ``type`` on an existing SqlServerConfig is not enough: its
        ``database`` attribute (e.g. "master") takes priority over ``url`` in
        the SQLite connection manager, causing the DB to be written to a file
        named "master" in the CWD instead of the path in the URL.
        Creating a fresh SQLiteConfig avoids this.
        """
        if not overrides.get("url"):
            return None
        _url_lower = overrides["url"].lower()
        if not _url_lower.startswith(("sqlite:", "sqlite3:")):
            return None
        sqlite_data: Dict[str, Any] = {
            "type": "sqlite",  # lint: allow-dialect-string: dialect dispatch
            "url": overrides["url"],
            "schema": overrides.get("schema", base_config.schema) or "main",
        }
        try:
            return BaseDatabaseConfig.create(sqlite_data)
        except ValueError:
            return None

    @staticmethod
    def build_from_dict(config_dict: Dict[str, Any]) -> BaseDatabaseConfig:
        """Build database configuration from dictionary.

        Args:
            config_dict: Dictionary containing configuration values

        Returns:
            Database configuration object

        Raises:
            ConfigurationError: If required fields are missing or invalid
        """
        if "type" not in config_dict:
            raise ConfigurationError("Database type is required in configuration")

        try:
            return BaseDatabaseConfig.create(config_dict)
        except ValueError as e:
            raise ConfigurationError(f"Failed to create database configuration: {e}") from e

    @staticmethod
    def validate_required_fields(config: BaseDatabaseConfig) -> None:
        """Validate that required configuration fields are present.

        Args:
            config: Database configuration to validate

        Raises:
            ConfigurationError: If required fields are missing
        """
        if not config.url:
            raise ConfigurationError("Database URL is required")

        # Check if username/password are in URL or as separate fields
        from core.utils.database_url_parser import DatabaseUrlParser

        url_username = DatabaseUrlParser.parse_username(config.url)
        url_password = DatabaseUrlParser.parse_password(config.url)

        if not config.username and not url_username:
            raise ConfigurationError("Database username is required")

        if not config.password and not url_password:
            raise ConfigurationError("Database password is required")

        from db.provider_registry import ProviderRegistry

        quirks = ProviderRegistry.get_quirks((config.type or "").lower())
        if not config.schema:
            derived_schema = quirks.derive_schema_name(config)
            if derived_schema:
                config.schema = derived_schema

        if quirks.schema_required and not config.schema:
            raise ConfigurationError("Database schema is required")

    @classmethod
    def build(
        cls, file_path: Optional[Union[str, Path]] = None, env_overrides: bool = True, **kwargs: Any
    ) -> DbliftConfig:
        """Unified configuration builder.

        Builds configuration from multiple sources with precedence:
        1. kwargs (highest priority)
        2. Environment variables (if env_overrides=True)
        3. Config file (if file_path provided)

        Args:
            file_path: Path to config file
            env_overrides: Whether to apply environment variable overrides
            **kwargs: Configuration overrides (database_url, database_schema, etc.)

        Returns:
            DbliftConfig instance

        Example:
            >>> # From file with overrides
            >>> config = ConfigBuilder.build(
            ...     file_path="dblift.yaml",
            ...     database_url="postgresql+psycopg://localhost/mydb",
            ...     database_schema="public"
            ... )

            >>> # From environment variables only
            >>> config = ConfigBuilder.build(env_overrides=True)

            >>> # From kwargs only
            >>> config = ConfigBuilder.build(
            ...     database_url="postgresql+psycopg://localhost/mydb",
            ...     database_schema="public"
            ... )
        """
        config_data: Dict[str, Any] = {}

        # Load from file if provided. Raw data from every source is merged before
        # constructing the typed config, so database type is selected only once.
        if file_path:
            file_path_str = str(file_path)
            if not Path(file_path_str).exists():
                raise FileNotFoundError(f"Config file not found: {file_path_str}")
            try:
                file_data = DbliftConfig.load_config_data_from_yaml(file_path_str)
                if file_data:
                    config_data = DbliftConfig.merge_config_data(config_data, file_data)
            except FileNotFoundError:
                raise
            except Exception as e:
                warnings.warn(
                    f"Failed to load config file '{file_path_str}': {e}",
                    stacklevel=2,
                )

        # Apply environment variables if enabled.
        # Merge the raw env dict directly — bypassing from_env() which requires
        # DBLIFT_DB_URL and rejects partial env-only configs otherwise.
        # Merging the raw env dict keeps the guard and the actual merge in sync:
        # only values that env actually provided participate in precedence.
        if env_overrides:
            env_dict = DbliftConfig.from_env_dict()
            if env_dict:
                config_data = DbliftConfig.merge_config_data(config_data, env_dict)

        # Apply kwargs overrides
        if kwargs:
            # Convert kwargs to proper config dict format
            kwargs_dict: dict[str, Any] = {}
            # Map common kwargs to config structure
            if "database_url" in kwargs or "db_url" in kwargs:
                if "database" not in kwargs_dict:
                    kwargs_dict["database"] = {}
                kwargs_dict["database"]["url"] = kwargs.get("database_url") or kwargs.get("db_url")
            if "database_username" in kwargs or "db_username" in kwargs:
                if "database" not in kwargs_dict:
                    kwargs_dict["database"] = {}
                kwargs_dict["database"]["username"] = kwargs.get("database_username") or kwargs.get(
                    "db_username"
                )
            if "database_password" in kwargs or "db_password" in kwargs:
                if "database" not in kwargs_dict:
                    kwargs_dict["database"] = {}
                kwargs_dict["database"]["password"] = kwargs.get("database_password") or kwargs.get(
                    "db_password"
                )
            if "database_schema" in kwargs or "db_schema" in kwargs:
                if "database" not in kwargs_dict:
                    kwargs_dict["database"] = {}
                kwargs_dict["database"]["schema"] = kwargs.get("database_schema") or kwargs.get(
                    "db_schema"
                )
            if "database_type" in kwargs or "db_type" in kwargs:
                if "database" not in kwargs_dict:
                    kwargs_dict["database"] = {}
                kwargs_dict["database"]["type"] = kwargs.get("database_type") or kwargs.get(
                    "db_type"
                )
            for field in (
                "account_endpoint",
                "account_key",
                "database",
                "database_name",
                "container_name",
                "use_managed_identity",
            ):
                if field in kwargs:
                    if "database" not in kwargs_dict:
                        kwargs_dict["database"] = {}
                    kwargs_dict["database"][field] = kwargs[field]

            # Map other top-level kwargs
            for key in [
                "history_table",
                "snapshot_table",
                "max_snapshots",
                "log_level",
                "log_file",
                "log_dir",
                "log_format",
            ]:
                if key in kwargs:
                    kwargs_dict[key] = kwargs[key]

            if kwargs_dict:
                config_data = DbliftConfig.merge_config_data(config_data, kwargs_dict)

        if not config_data:
            raise ConfigurationError(
                "No configuration source provided. Pass --config, --db-url, or set DBLIFT_DB_URL."
            )

        return cls.from_dict(config_data)

    @classmethod
    def from_file(cls, path: Optional[Union[str, Path]] = None) -> DbliftConfig:
        """Load config from file.

        Args:
            path: Path to config file (uses default if None)

        Returns:
            DbliftConfig instance

        Raises:
            FileNotFoundError: If config file does not exist
        """
        if path is None:
            # Try default locations
            default_paths = ["dblift.yaml", "dblift.yml", ".dblift.yaml"]
            for default_path in default_paths:
                if Path(default_path).exists():
                    path = default_path
                    break

        if path is None:
            raise ConfigurationError(
                "No configuration file found. Pass a config path or provide database settings."
            )

        return DbliftConfig.from_file(path)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> DbliftConfig:
        """Build config from dictionary.

        Args:
            config_dict: Configuration dictionary

        Returns:
            DbliftConfig instance

        Example:
            >>> config = ConfigBuilder.from_dict({
            ...     "database": {
            ...         "url": "postgresql+psycopg://localhost/mydb",
            ...         "schema": "public"
            ...     }
            ... })
        """
        return DbliftConfig.from_dict(config_dict)

    @classmethod
    def from_env(cls) -> DbliftConfig:
        """Build config from environment variables.

        Returns:
            DbliftConfig instance (default if no env vars set)

        Example:
            >>> # Set environment variables
            >>> os.environ["DBLIFT_DB_URL"] = "postgresql+psycopg://localhost/mydb"
            >>> os.environ["DBLIFT_DB_SCHEMA"] = "public"
            >>> config = ConfigBuilder.from_env()
        """
        env_dict = DbliftConfig.from_env_dict()
        if env_dict:
            return DbliftConfig.from_dict(env_dict)
        raise ConfigurationError(
            "No environment configuration found. Set DBLIFT_DB_URL or DBLIFT_DB_TYPE."
        )

    @classmethod
    def merge(cls, *configs: DbliftConfig) -> DbliftConfig:
        """Merge multiple configs (later overrides earlier).

        Args:
            *configs: Config instances to merge

        Returns:
            Merged DbliftConfig instance

        Example:
            >>> base = ConfigBuilder.from_file("base.yaml")
            >>> override = ConfigBuilder.from_dict({"database": {"schema": "custom"}})
            >>> merged = ConfigBuilder.merge(base, override)
        """
        if not configs:
            raise ConfigurationError("At least one configuration is required to merge")

        # Start with first config
        result = configs[0]

        # Merge each subsequent config
        for config in configs[1:]:
            # Convert to dict and merge
            config_dict = config.to_dict()
            result.merge(config_dict)

        return result
