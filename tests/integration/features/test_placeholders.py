"""
Test placeholder functionality through CLI.

CRITICAL: These tests verify that placeholders work correctly in migrations
and callbacks, with values specified via:
- YAML configuration
- Command line arguments (--placeholders)

All tests use the production CLI (cli/main.py) to ensure
placeholders work end-to-end in real migrations.
"""

from pathlib import Path

import pytest

from tests.integration.helpers.cli_runner_direct import DBLiftCLIDirect as DBLiftCLI
from tests.integration.helpers.database_helper import (
    execute_query,
    verify_table_exists,
)
from tests.integration.helpers.migration_helper import create_migration


@pytest.mark.integration
class TestPlaceholders:
    """Test placeholder functionality through CLI."""

    def test_placeholder_in_migration_via_cli(self, postgresql_container, tmp_path):
        """Test placeholders specified via CLI arguments work in migrations."""
        from tests.integration.helpers.migration_helper import create_config

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create migration with placeholders
        sql_script = """
        CREATE SCHEMA IF NOT EXISTS ${table_schema};
        
        CREATE TABLE ${table_schema}.users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100),
            environment VARCHAR(50) DEFAULT '${env_name}'
        );
        
        INSERT INTO ${table_schema}.users (username, environment)
        VALUES ('admin', '${env_name}');
        """

        create_migration(migrations_dir, "V1_0_0__with_placeholders.sql", sql_script)

        # Execute migration with placeholders via CLI
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(placeholders="table_schema=test_schema,env_name=production")

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(postgresql_container, "users", schema="test_schema")

    def test_placeholder_in_migration_via_config(self, postgresql_container, tmp_path):
        """Test placeholders specified in YAML config work in migrations."""
        from tests.integration.helpers.migration_helper import create_config

        database_url = (
            f"postgresql+psycopg://{postgresql_container['host']}:"
            f"{postgresql_container['port']}/{postgresql_container['database']}"
        )

        # Create config with placeholders
        config_content = f"""
database:
  url: {database_url}
  schema: public
  username: {postgresql_container['username']}
  password: {postgresql_container['password']}

placeholders:
  app_schema: app_data
  app_version: "1.0.0"
  deploy_user: deploy_admin
"""
        config_file = tmp_path / "dblift.yaml"
        config_file.write_text(config_content)

        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        sql_script = """
        CREATE SCHEMA IF NOT EXISTS ${app_schema};
        
        CREATE TABLE ${app_schema}.app_info (
            id SERIAL PRIMARY KEY,
            version VARCHAR(50) DEFAULT '${app_version}',
            deployed_by VARCHAR(100) DEFAULT '${deploy_user}'
        );
        
        INSERT INTO ${app_schema}.app_info (version, deployed_by)
        VALUES ('${app_version}', '${deploy_user}');
        """

        create_migration(migrations_dir, "V1_0_0__app_info.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(postgresql_container, "app_info", schema="app_data")

    def test_placeholder_with_default_value(self, postgresql_container, tmp_path):
        """Test placeholders with default values work correctly."""
        from tests.integration.helpers.migration_helper import create_config

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Migration with placeholder that has a default value
        sql_script = """
        CREATE TABLE config (
            id SERIAL PRIMARY KEY,
            environment VARCHAR(50) DEFAULT '${env:development}',
            debug_mode VARCHAR(10) DEFAULT '${debug:false}'
        );
        
        INSERT INTO config (environment, debug_mode)
        VALUES ('${env:development}', '${debug:false}');
        """

        create_migration(migrations_dir, "V1_0_0__with_defaults.sql", sql_script)

        # Execute without providing placeholders - should use defaults
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_system_placeholders(self, postgresql_container, tmp_path):
        """Test that system-provided placeholders (dblift_*) work correctly."""
        from tests.integration.helpers.migration_helper import create_config

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Migration using system placeholders
        sql_script = """
        CREATE TABLE metadata (
            id SERIAL PRIMARY KEY,
            schema_name VARCHAR(100),
            username VARCHAR(100),
            migration_date VARCHAR(50)
        );
        
        INSERT INTO metadata (schema_name, username, migration_date)
        VALUES ('${dblift_schema}', '${dblift_username}', '${dblift_date}');
        """

        create_migration(migrations_dir, "V1_0_0__system_placeholders.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(postgresql_container, "metadata")

    def test_cli_placeholders_override_config(self, postgresql_container, tmp_path):
        """Test that CLI placeholders override config placeholders."""
        from tests.integration.helpers.migration_helper import create_config

        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        # Use the same schema as postgresql_container / cleanup_database (TEST_SCHEMA), not public —
        # cleanup only drops objects in the container schema; using public leaves history/objects
        # behind and can cause migrate to skip while verification expects a table that was never
        # created in this run.
        config_file = create_config(
            tmp_path,
            postgresql_container,
            migrations_dir=migrations_dir,
            placeholders={"env_name": "config_env", "version": "1.0.0"},
        )

        sql_script = """
        CREATE TABLE deployment (
            id SERIAL PRIMARY KEY,
            environment VARCHAR(100),
            version VARCHAR(50)
        );
        
        INSERT INTO deployment (environment, version)
        VALUES ('${env_name}', '${version}');
        """

        create_migration(migrations_dir, "V1_0_0__deployment.sql", sql_script)

        # CLI placeholders should override config
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(placeholders="env_name=cli_env,version=2.0.0")

        assert result.success, f"Failed: {result.stderr}"

        # Verify the CLI value was used
        schema = postgresql_container.get("schema", "TEST_SCHEMA")
        query_result = execute_query(
            postgresql_container,
            f'SELECT environment, version FROM "{schema}".deployment',
        )
        assert len(query_result) == 1
        assert query_result[0]["environment"] == "cli_env"
        assert query_result[0]["version"] == "2.0.0"

    def test_placeholder_in_callbacks(self, postgresql_container, tmp_path):
        """Test placeholders work in callback scripts."""
        from tests.integration.helpers.migration_helper import create_config

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create beforeMigrate callback with placeholders
        callback_script = """
        CREATE TABLE ${callback_schema}.callback_log (
            id SERIAL PRIMARY KEY,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        INSERT INTO ${callback_schema}.callback_log (message)
        VALUES ('Migration started for ${env_name}');
        """

        # Note: Callbacks use different naming convention
        create_migration(migrations_dir, "beforemigrate__setup_logging.sql", callback_script)

        # Regular migration
        migration_script = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100)
        );
        """

        create_migration(migrations_dir, "V1_0_0__users.sql", migration_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(placeholders="callback_schema=public,env_name=test_env")

        assert result.success, f"Failed: {result.stderr}"

    def test_placeholder_in_string_literals(self, postgresql_container, tmp_path):
        """Test placeholders inside string literals are replaced."""
        from tests.integration.helpers.migration_helper import create_config

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE messages (
            id SERIAL PRIMARY KEY,
            message TEXT
        );
        
        INSERT INTO messages (message)
        VALUES ('Application: ${app_name}, Version: ${app_version}, Environment: ${env}');
        """

        create_migration(migrations_dir, "V1_0_0__messages.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(placeholders="app_name=DBLift,app_version=1.0.0,env=production")

        assert result.success, f"Failed: {result.stderr}"

        # Verify the placeholder was replaced
        schema = postgresql_container.get("schema", "TEST_SCHEMA")
        query_result = execute_query(
            postgresql_container, f'SELECT message FROM "{schema}".messages'
        )
        assert len(query_result) > 0, f"No rows found in {schema}.messages table"
        assert "DBLift" in query_result[0]["message"]
        assert "1.0.0" in query_result[0]["message"]
        assert "production" in query_result[0]["message"]

    def test_multiple_placeholder_formats(self, postgresql_container, tmp_path):
        """Test mixing placeholders with and without defaults."""
        from tests.integration.helpers.migration_helper import create_config

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE app_config (
            id SERIAL PRIMARY KEY,
            required_value VARCHAR(100),
            optional_value VARCHAR(100),
            default_value VARCHAR(100)
        );
        
        -- Mix of required and optional placeholders
        INSERT INTO app_config (required_value, optional_value, default_value)
        VALUES ('${required_param}', '${optional_param:default_opt}', '${another:default_val}');
        """

        create_migration(migrations_dir, "V1_0_0__mixed_placeholders.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        # Only provide required_param, others should use defaults
        result = cli.migrate(placeholders="required_param=required_value")

        assert result.success, f"Failed: {result.stderr}"

        # Verify values
        schema = postgresql_container.get("schema", "TEST_SCHEMA")
        query_result = execute_query(
            postgresql_container,
            f'SELECT required_value, optional_value, default_value FROM "{schema}".app_config',
        )
        assert len(query_result) > 0, f"No rows found in {schema}.app_config table"
        assert query_result[0]["required_value"] == "required_value"
        assert query_result[0]["optional_value"] == "default_opt"
        assert query_result[0]["default_value"] == "default_val"

    def test_placeholder_in_undo_migration(self, postgresql_container, tmp_path):
        """Test placeholders work in undo migrations."""
        from tests.integration.helpers.migration_helper import create_config

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Forward migration with placeholder
        forward_script = """
        CREATE TABLE ${schema_name}.test_table (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100)
        );
        """

        # Undo migration with placeholder
        undo_script = """
        DROP TABLE ${schema_name}.test_table;
        """

        create_migration(migrations_dir, "V1_0_0__create_table.sql", forward_script)
        create_migration(migrations_dir, "U1_0_0__create_table.sql", undo_script)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Apply migration
        result = cli.migrate(placeholders="schema_name=public")
        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(postgresql_container, "test_table", schema="public")

        # Undo migration
        result = cli.undo(placeholders="schema_name=public")
        assert result.success, f"Failed: {result.stderr}"
        assert not verify_table_exists(postgresql_container, "test_table", schema="public")

    def test_placeholder_with_special_characters(self, postgresql_container, tmp_path):
        """Test placeholders with special characters in values."""
        from tests.integration.helpers.migration_helper import create_config

        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE special_data (
            id SERIAL PRIMARY KEY,
            data TEXT
        );
        
        INSERT INTO special_data (data)
        VALUES ('${special_value}');
        """

        create_migration(migrations_dir, "V1_0_0__special.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        # Test with special characters (note: escaping might be needed)
        result = cli.migrate(placeholders="special_value=value_with-dashes_and.dots")

        assert result.success, f"Failed: {result.stderr}"
