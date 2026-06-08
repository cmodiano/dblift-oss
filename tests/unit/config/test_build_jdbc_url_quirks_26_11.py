"""Story 26-11: database URL behaviour uses plugin-owned quirks."""

import inspect

import pytest

from config.database_config import BaseDatabaseConfig

pytestmark = [pytest.mark.unit]


class TestBuildDatabaseUrlNoHardcodedDialect:
    """AC#1: BaseDatabaseConfig.build_database_url has no hardcoded dialect checks."""

    def test_no_sqlserver_string_in_base_build_database_url(self):
        src = inspect.getsource(BaseDatabaseConfig.build_database_url)
        assert '"sqlserver"' not in src

    def test_uses_provider_registry(self):
        src = inspect.getsource(BaseDatabaseConfig.build_database_url)
        assert "ProviderRegistry.build_sqlalchemy_url" in src


class TestQuirksPropertiesPerDialect:
    """AC#2: quirks properties expose native-driver behaviour per dialect."""

    def test_postgresql_quirks_lint_placeholder_url(self):
        from db.provider_registry import ProviderRegistry

        quirks = ProviderRegistry.get_quirks("postgresql")
        assert quirks.lint_placeholder_url.startswith("postgresql://")

    def test_mysql_quirks_native_driver_display(self):
        from db.provider_registry import ProviderRegistry

        quirks = ProviderRegistry.get_quirks("mysql")
        assert quirks.native_driver_display is not None

    def test_sqlite_quirks_not_none(self):
        from db.provider_registry import ProviderRegistry

        quirks = ProviderRegistry.get_quirks("sqlite")
        assert quirks is not None
