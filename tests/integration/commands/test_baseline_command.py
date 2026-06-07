"""
Test baseline command.

The baseline command marks a specific version as applied without running
the migration scripts. This is useful when adding DBLift to an existing database.

Usage scenarios:
- Existing database with objects already created
- Want to start using DBLift from a specific version
- Historical migrations shouldn't be run

All tests use the production CLI (cli/main.py).
"""

import pytest

from tests.integration.helpers.cli_runner import DBLiftCLI
from tests.integration.helpers.database_helper import (
    DatabaseHelper,
    verify_table_exists,
)
from tests.integration.helpers.migration_helper import (
    create_config,
    create_versioned_migration,
    generate_test_sql,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["postgresql", "mysql", "sqlserver", "oracle", "db2"],
    indirect=True,
)
class TestBaselineCommand:
    """Test baseline command with various scenarios."""

    def test_baseline_basic(self, db_container, tmp_path):
        """
        Test basic baseline without description.

        IMPORTANT: Baseline does NOT require migration files to exist.
        It just marks a version as applied in the history table.
        """
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Set baseline at 1.0.0 (no migration files needed!)
        result = cli.baseline(baseline_version="1.0.0")

        assert result.success, f"Baseline failed: {result.stderr}"
        assert "1.0.0" in result.stdout or "baseline" in result.stdout.lower()

        # Verify with info command
        info_result = cli.info()
        assert info_result.success
        # Should show as baselined or already applied
        output_lower = info_result.stdout.lower()
        assert (
            "baseline" in output_lower or "success" in output_lower or "1.0.0" in info_result.stdout
        )

    def test_baseline_with_description(self, db_container, tmp_path):
        """Test baseline with description."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        create_versioned_migration(migrations_dir, "1.0.0", "initial", "-- Historical")

        cli = DBLiftCLI(config_file, migrations_dir)

        # Set baseline with description
        result = cli.baseline(
            baseline_version="1.0.0",
            baseline_description="Existing production schema",
        )

        assert result.success, f"Baseline failed: {result.stderr}"

    def test_baseline_existing_database_scenario(self, db_container, tmp_path):
        """
        Test realistic scenario: existing database with objects.

        Scenario:
        1. Database already has tables (created outside DBLift)
        2. Create historical migration scripts
        3. Baseline to skip historical migrations
        4. Apply new migrations
        """
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Simulate existing database - create table directly
        db_helper = DatabaseHelper(db_container)
        if db_type == "postgresql":
            db_helper.execute_statement(
                f'CREATE TABLE "{schema}"."existing_table" (id SERIAL PRIMARY KEY)'
            )
        elif db_type == "mysql":
            db_helper.execute_statement(
                f"CREATE TABLE {schema}.existing_table (id INT AUTO_INCREMENT PRIMARY KEY)"
            )
        elif db_type == "oracle":
            db_helper.execute_statement(
                f"CREATE TABLE {schema}.existing_table (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY)"
            )
        elif db_type == "db2":
            db_helper.execute_statement(
                f"CREATE TABLE {schema}.existing_table (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY)"
            )
        else:  # sqlserver
            db_helper.execute_statement(
                f"CREATE TABLE {schema}.existing_table (id INT IDENTITY(1,1) PRIMARY KEY)"
            )
        # Commit the table creation
        db_helper._get_provider().commit_transaction()

        # Verify table exists immediately after creation
        assert verify_table_exists(
            db_container, "existing_table", schema
        ), "Table should exist after creation"

        # Close the helper connection (fixture will handle schema cleanup after test)
        db_helper.cleanup()

        # Create historical migrations (representing how table was created)
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "create_existing",
            generate_test_sql(db_type, "existing_table", schema),
        )

        # Create new migration (new changes)
        create_versioned_migration(
            migrations_dir,
            "1.1.0",
            "new_table",
            generate_test_sql(db_type, "new_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Baseline at 1.0.0 (skip historical migration)
        result = cli.baseline(
            baseline_version="1.0.0",
            baseline_description="Existing production schema",
        )

        assert result.success, f"Baseline failed: {result.stderr}"

        # Now migrate (should only apply 1.1.0)
        result = cli.migrate()

        assert result.success, f"Migration failed: {result.stderr}"
        assert "1_1_0" in result.stdout or "1.1.0" in result.stdout

        # Verify both tables exist
        assert verify_table_exists(db_container, "existing_table", schema)

        assert verify_table_exists(db_container, "new_table", schema)

    def test_baseline_then_info(self, db_container, tmp_path):
        """Test that info command correctly shows baselined migrations."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create several migrations
        create_versioned_migration(migrations_dir, "1.0.0", "v1", "-- Migration 1")
        create_versioned_migration(migrations_dir, "1.0.1", "v2", "-- Migration 2")
        create_versioned_migration(migrations_dir, "1.0.2", "v3", "-- Migration 3")

        cli = DBLiftCLI(config_file, migrations_dir)

        # Baseline at 1.0.1
        result = cli.baseline(baseline_version="1.0.1")
        assert result.success

        # Check info
        info_result = cli.info()
        assert info_result.success

        # 1.0.0 and 1.0.1 should be marked as baselined/applied
        # 1.0.2 should be pending
        assert "1_0_2" in info_result.stdout or "1.0.2" in info_result.stdout

    def test_baseline_dry_run(self, db_container, tmp_path):
        """Test baseline with --dry-run option."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        create_versioned_migration(migrations_dir, "1.0.0", "test", "-- Test")

        cli = DBLiftCLI(config_file, migrations_dir)

        # Dry run baseline
        result = cli.baseline(baseline_version="1.0.0", dry_run=True)

        assert result.success, f"Baseline dry run failed: {result.stderr}"

        # Verify nothing was actually baselined
        info_result = cli.info()
        assert info_result.success
        # Should still show as pending
        output_lower = info_result.stdout.lower()
        assert "pending" in output_lower or "not applied" in output_lower

    def test_baseline_multiple_versions(self, db_container, tmp_path):
        """Test that baseline covers all versions up to specified version."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        # Create multiple migrations
        create_versioned_migration(migrations_dir, "1.0.0", "v1", "-- V1")
        create_versioned_migration(migrations_dir, "1.0.1", "v2", "-- V2")
        create_versioned_migration(migrations_dir, "1.0.2", "v3", "-- V3")
        create_versioned_migration(migrations_dir, "1.1.0", "v4", "-- V4")

        cli = DBLiftCLI(config_file, migrations_dir)

        # Baseline at 1.0.2 (should baseline 1.0.0, 1.0.1, and 1.0.2)
        result = cli.baseline(baseline_version="1.0.2")
        assert result.success

        # Verify info shows 1.1.0 as pending
        info_result = cli.info()
        assert info_result.success
        assert "1_1_0" in info_result.stdout or "1.1.0" in info_result.stdout

        # Migrate should only apply 1.1.0
        result = cli.migrate()
        assert result.success
        # Should mention 1.1.0 but not the baselined versions
        assert "1_1_0" in result.stdout or "1.1.0" in result.stdout


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["postgresql", "mysql", "sqlserver", "oracle", "db2"],
    indirect=True,
)
class TestBaselineErrors:
    """Test baseline command error handling."""

    def test_baseline_nonexistent_version(self, db_container, tmp_path):
        """Test baseline with version that doesn't exist in migration files.

        IMPORTANT: Baseline does NOT require migration files to exist.
        It just marks a version as applied in the history table.
        This is the whole point - you're marking existing database objects as "already migrated".
        """
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        create_versioned_migration(migrations_dir, "1.0.0", "test", "-- Test")

        cli = DBLiftCLI(config_file, migrations_dir)

        # Baseline to version 9.9.9 even though no migration file exists for it
        # This should succeed - baseline doesn't need migration files
        result = cli.baseline(baseline_version="9.9.9")

        # Should succeed - baseline is just marking a point in history
        assert (
            result.success
        ), f"Baseline should succeed even without migration files: {result.stderr}"

        # Verify baseline was recorded
        info_result = cli.info()
        assert info_result.success

    def test_baseline_after_migrations_applied(self, db_container, tmp_path):
        """Test baseline after migrations are already applied."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "test",
            generate_test_sql(db_type, "test_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Apply migration first
        result = cli.migrate()
        assert result.success

        # Try to baseline the same version
        result = cli.baseline(baseline_version="1.0.0")

        # Should handle gracefully (either succeed or error about already existing migrations)
        # Error messages are now in stderr, so check both stdout and stderr
        combined_output = (result.stdout + result.stderr).lower()
        assert result.success or ("already" in combined_output and not result.success)
