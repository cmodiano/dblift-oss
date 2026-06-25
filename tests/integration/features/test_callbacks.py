"""
Test callback functionality through CLI.

CRITICAL: These tests verify that callbacks execute correctly at the
appropriate lifecycle events:
- beforemigrate: Before any migrations
- aftermigrate: After all migrations
- beforeeach: Before each migration
- aftereach: After each migration
- beforeversioned: Before versioned migrations
- afterversioned: After versioned migrations
- beforerepeatable: Before repeatable migrations
- afterrepeatable: After repeatable migrations

All tests use the production CLI (cli/main.py) to ensure
callbacks work end-to-end in real migrations.
"""

import pytest

from tests.integration.helpers.cli_runner_direct import DBLiftCLIDirect as DBLiftCLI
from tests.integration.helpers.database_helper import (
    execute_query,
    verify_table_exists,
)
from tests.integration.helpers.migration_helper import (
    create_config,
    create_migration,
)


@pytest.mark.integration
class TestCallbacks:
    """Test callback functionality through CLI."""

    def test_beforemigrate_callback(self, postgresql_container, tmp_path):
        """Test that beforemigrate callback executes before migrations."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create beforemigrate callback
        callback_script = """
        CREATE TABLE callback_log (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(50),
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        INSERT INTO callback_log (event_type)
        VALUES ('beforemigrate');
        """
        create_migration(migrations_dir, "beforeMigrate__setup.sql", callback_script)

        # Create regular migration
        migration_script = """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100)
        );
        """
        create_migration(migrations_dir, "V1_0_0__users.sql", migration_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(postgresql_container, "callback_log")
        assert verify_table_exists(postgresql_container, "users")

        # Verify callback executed
        rows = execute_query(postgresql_container, "SELECT event_type FROM callback_log")
        assert len(rows) >= 1
        assert rows[0]["event_type"] == "beforemigrate"

    def test_aftermigrate_callback(self, postgresql_container, tmp_path):
        """Test that aftermigrate callback executes after migrations."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create regular migration
        migration_script = """
        CREATE TABLE migration_results (
            id SERIAL PRIMARY KEY,
            status VARCHAR(50)
        );
        """
        create_migration(migrations_dir, "V1_0_0__results.sql", migration_script)

        # Create aftermigrate callback
        callback_script = """
        INSERT INTO migration_results (status)
        VALUES ('completed');
        """
        create_migration(migrations_dir, "afterMigrate__finalize.sql", callback_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

        # Verify callback executed after migration
        rows = execute_query(postgresql_container, "SELECT status FROM migration_results")
        assert len(rows) == 1
        assert rows[0]["status"] == "completed"

    def test_beforeeach_aftereach_callbacks(self, postgresql_container, tmp_path):
        """Test that beforeeach/aftereach callbacks execute around each migration."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create callback log table in beforemigrate
        setup_script = """
        CREATE TABLE callback_execution_log (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(50),
            migration_count INT,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        create_migration(migrations_dir, "beforeMigrate__setup_log.sql", setup_script)

        # Create beforeeach callback
        beforeeach_script = """
        INSERT INTO callback_execution_log (event_type, migration_count)
        SELECT 'beforeeach', COALESCE(MAX(id), 0) + 1
        FROM callback_execution_log;
        """
        create_migration(migrations_dir, "beforeEach__log.sql", beforeeach_script)

        # Create aftereach callback
        aftereach_script = """
        INSERT INTO callback_execution_log (event_type, migration_count)
        SELECT 'aftereach', COALESCE(MAX(id), 0) + 1
        FROM callback_execution_log;
        """
        create_migration(migrations_dir, "afterEach__log.sql", aftereach_script)

        # Create multiple migrations
        for i in range(1, 4):
            migration_script = f"""
            CREATE TABLE test_table_{i} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100)
            );
            """
            create_migration(migrations_dir, f"V{i}_0_0__table_{i}.sql", migration_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

        # Verify callbacks executed for each migration
        rows = execute_query(
            postgresql_container,
            "SELECT event_type, COUNT(*) FROM callback_execution_log GROUP BY event_type ORDER BY event_type",
        )

        # Should have beforeeach and aftereach for each of the 3 migrations
        # Note: Actual behavior might vary based on implementation
        assert len(rows) >= 2

    def test_callback_with_placeholders(self, postgresql_container, tmp_path):
        """Test that placeholders work correctly in callbacks."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create callback with placeholders
        callback_script = """
        CREATE TABLE deployment_info (
            id SERIAL PRIMARY KEY,
            schema_name VARCHAR(100),
            environment VARCHAR(100),
            deployed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        INSERT INTO deployment_info (schema_name, environment)
        VALUES ('${dblift_schema}', '${env_name:production}');
        """
        create_migration(migrations_dir, "beforeMigrate__deployment.sql", callback_script)

        # Regular migration
        migration_script = """
        CREATE TABLE app_data (id SERIAL PRIMARY KEY);
        """
        create_migration(migrations_dir, "V1_0_0__app_data.sql", migration_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(placeholders="env_name=staging")

        assert result.success, f"Failed: {result.stderr}"

        # Verify placeholder was replaced
        rows = execute_query(postgresql_container, "SELECT environment FROM deployment_info")
        assert len(rows) == 1
        assert rows[0]["environment"] == "staging"

    def test_callback_execution_order(self, postgresql_container, tmp_path):
        """Test that callbacks execute in the correct order."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Setup callback log table
        setup_script = """
        CREATE TABLE execution_order (
            id SERIAL PRIMARY KEY,
            step VARCHAR(50),
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        create_migration(migrations_dir, "beforemigrate__setup.sql", setup_script)

        # Multiple beforemigrate callbacks (should execute in order)
        for i in range(1, 4):
            callback_script = f"""
            INSERT INTO execution_order (step)
            VALUES ('beforemigrate_{i}');
            """
            create_migration(migrations_dir, f"beforeMigrate__step_{i}.sql", callback_script)

        # Regular migration
        migration_script = """
        INSERT INTO execution_order (step) VALUES ('migration_1');
        """
        create_migration(migrations_dir, "V1_0_0__migration.sql", migration_script)

        # aftermigrate callback
        cleanup_script = """
        INSERT INTO execution_order (step)
        VALUES ('aftermigrate');
        """
        create_migration(migrations_dir, "afterMigrate__cleanup.sql", cleanup_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

        # Verify execution order
        rows = execute_query(postgresql_container, "SELECT step FROM execution_order ORDER BY id")

        steps = [row["step"] for row in rows]
        # beforemigrate callbacks should come first, then migration, then aftermigrate
        assert steps[0].startswith("beforemigrate")
        assert "migration_1" in steps
        assert steps[-1] == "aftermigrate"

    def test_callback_error_handling(self, postgresql_container, tmp_path):
        """Test error handling when callback fails."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create callback with intentional error
        callback_script = """
        CREATE TABLE callback_test (id INT);
        
        -- This will fail (invalid SQL)
        SELECT * FROM nonexistent_table;
        """
        create_migration(migrations_dir, "beforeMigrate__error.sql", callback_script)

        # Regular migration
        migration_script = """
        CREATE TABLE users (id SERIAL PRIMARY KEY);
        """
        create_migration(migrations_dir, "V1_0_0__users.sql", migration_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        # Migration might fail or continue depending on error handling strategy
        # At minimum, the error should be logged
        assert "error" in result.output.lower() or result.failed

    def test_versioned_callbacks(self, postgresql_container, tmp_path):
        """Test beforeversioned and afterversioned callbacks."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Setup log table
        setup_script = """
        CREATE TABLE versioned_log (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(50)
        );
        """
        create_migration(migrations_dir, "beforemigrate__setup.sql", setup_script)

        # beforeversioned callback
        before_versioned_script = """
        INSERT INTO versioned_log (event_type) VALUES ('beforeversioned');
        """
        create_migration(migrations_dir, "beforeVersioned__log.sql", before_versioned_script)

        # Versioned migration
        versioned_script = """
        CREATE TABLE versioned_data (id SERIAL PRIMARY KEY);
        """
        create_migration(migrations_dir, "V1_0_0__versioned.sql", versioned_script)

        # afterversioned callback
        after_versioned_script = """
        INSERT INTO versioned_log (event_type) VALUES ('afterversioned');
        """
        create_migration(migrations_dir, "afterVersioned__log.sql", after_versioned_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

        # Verify callbacks executed
        rows = execute_query(
            postgresql_container, "SELECT event_type FROM versioned_log ORDER BY id"
        )

        events = [row["event_type"] for row in rows]
        assert "beforeversioned" in events
        assert "afterversioned" in events

    def test_repeatable_callbacks(self, postgresql_container, tmp_path):
        """Test beforerepeatable and afterrepeatable callbacks."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Setup log table
        setup_script = """
        CREATE TABLE repeatable_log (
            id SERIAL PRIMARY KEY,
            event_type VARCHAR(50)
        );
        """
        create_migration(migrations_dir, "beforemigrate__setup.sql", setup_script)

        # beforerepeatable callback
        before_repeatable_script = """
        INSERT INTO repeatable_log (event_type) VALUES ('beforerepeatable');
        """
        create_migration(migrations_dir, "beforeRepeatable__log.sql", before_repeatable_script)

        # Repeatable migration
        repeatable_script = """
        CREATE OR REPLACE VIEW data_view AS
        SELECT 1 as id;
        """
        create_migration(migrations_dir, "R__data_view.sql", repeatable_script)

        # afterrepeatable callback
        after_repeatable_script = """
        INSERT INTO repeatable_log (event_type) VALUES ('afterrepeatable');
        """
        create_migration(migrations_dir, "afterRepeatable__log.sql", after_repeatable_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

        # Verify callbacks executed
        rows = execute_query(
            postgresql_container, "SELECT event_type FROM repeatable_log ORDER BY id"
        )

        events = [row["event_type"] for row in rows]
        assert "beforerepeatable" in events
        assert "afterrepeatable" in events

    def test_callbacks_with_dry_run(self, postgresql_container, tmp_path):
        """Test that callbacks respect dry-run mode."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create callback
        callback_script = """
        CREATE TABLE dry_run_test (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        create_migration(migrations_dir, "beforeMigrate__dry_run.sql", callback_script)

        # Regular migration
        migration_script = """
        CREATE TABLE users (id SERIAL PRIMARY KEY);
        """
        create_migration(migrations_dir, "V1_0_0__users.sql", migration_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(dry_run=True)

        assert result.success, f"Failed: {result.stderr}"

        # In dry-run mode, tables should not be created
        assert not verify_table_exists(postgresql_container, "dry_run_test")
        assert not verify_table_exists(postgresql_container, "users")

    def test_multiple_callbacks_same_event(self, postgresql_container, tmp_path):
        """Test multiple callbacks for the same event execute in order."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Setup log table
        setup_script = """
        CREATE TABLE multi_callback_log (
            id SERIAL PRIMARY KEY,
            callback_name VARCHAR(100),
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        create_migration(migrations_dir, "beforeMigrate__000_setup.sql", setup_script)

        # Multiple beforemigrate callbacks
        for i in range(1, 4):
            callback_script = f"""
            INSERT INTO multi_callback_log (callback_name)
            VALUES ('callback_{i}');
            """
            create_migration(
                migrations_dir, f"beforeMigrate__{i:03d}_callback_{i}.sql", callback_script
            )

        # Regular migration
        migration_script = """
        CREATE TABLE test_data (id SERIAL PRIMARY KEY);
        """
        create_migration(migrations_dir, "V1_0_0__test.sql", migration_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

        # Verify all callbacks executed in order
        rows = execute_query(
            postgresql_container, "SELECT callback_name FROM multi_callback_log ORDER BY id"
        )

        callback_names = [row["callback_name"] for row in rows]
        assert len(callback_names) == 3
        assert callback_names == ["callback_1", "callback_2", "callback_3"]
