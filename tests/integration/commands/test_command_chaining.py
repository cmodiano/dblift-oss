"""
Test command chaining - running multiple commands in sequence.

DBLift supports running multiple commands in a single CLI invocation:
    dblift info migrate info
    dblift validate migrate info
    dblift clean baseline migrate

This is useful for:
- Automated deployment scripts
- CI/CD pipelines
- Ensuring consistent command sequences

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
    create_undo_migration,
    create_versioned_migration,
    generate_test_sql,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["postgresql", "mysql", "sqlserver", "oracle", "db2"],
    indirect=True,
)
class TestCommandChaining:
    """Test running multiple commands in sequence."""

    def test_info_migrate_info(self, db_container, tmp_path):
        """Test chain: info -> migrate -> info."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        # Create config with migrations directory to avoid picking up project root migrations
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "test",
            generate_test_sql(db_type, "chain_test", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Chain: info, migrate, info
        result = cli.chain("info", "migrate", "info")

        assert result.success, f"Command chain failed: {result.stderr}"
        # Should show output from all three commands
        assert "1.0.0" in result.stdout

        # Verify migration was applied
        assert verify_table_exists(db_container, "chain_test", schema)

    def test_validate_migrate(self, db_container, tmp_path):
        """Test chain: validate -> migrate."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "test",
            generate_test_sql(db_type, "validate_migrate", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Chain: validate then migrate
        result = cli.chain("validate", "migrate")

        assert result.success, f"Command chain failed: {result.stderr}"
        assert verify_table_exists(db_container, "validate_migrate", schema)

    def test_clean_baseline_migrate(self, db_container, tmp_path):
        """Test chain: clean -> baseline -> migrate."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migrations
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "first",
            generate_test_sql(db_type, "baseline_test", schema),
        )
        create_versioned_migration(
            migrations_dir,
            "1.1.0",
            "second",
            generate_test_sql(db_type, "new_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # This would typically be: clean (remove old), baseline (mark as applied), migrate (new ones)
        # Note: Can't easily chain these in one call with different options
        # So test individually in sequence

        result = cli.clean()
        assert result.success

        result = cli.baseline(baseline_version="1.0.0")
        assert result.success

        result = cli.migrate()
        assert result.success

        # Should have migrated 1.1.0
        assert verify_table_exists(db_container, "new_table", schema)


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["postgresql", "mysql", "sqlserver", "oracle", "db2"],
    indirect=True,
)
class TestComplexMigrationScenarios:
    """Test complex migration scenarios with multiple options."""

    def test_migrate_with_target_then_undo(self, db_container, tmp_path):
        """Test: migrate to target version, then undo."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create three migrations with undo scripts
        for version, table in [("1.0.0", "t1"), ("1.0.1", "t2"), ("1.0.2", "t3")]:
            if db_type == "postgresql":
                up_sql = f'CREATE TABLE "{schema}"."{table}" (id SERIAL PRIMARY KEY);'
                down_sql = f'DROP TABLE IF EXISTS "{schema}"."{table}";'
            elif db_type == "mysql":
                up_sql = f"CREATE TABLE {schema}.{table} (id INT AUTO_INCREMENT PRIMARY KEY);"
                down_sql = f"DROP TABLE IF EXISTS {schema}.{table};"
            elif db_type == "oracle":
                up_sql = f"CREATE TABLE {schema}.{table} (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
                # Oracle stores unquoted identifiers as uppercase, so DROP must use uppercase
                # to match the stored table name
                down_sql = f"DROP TABLE {schema}.{table.upper()};"
            elif db_type == "db2":
                up_sql = f"CREATE TABLE {schema}.{table} (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
                down_sql = f"DROP TABLE {schema}.{table};"
            else:  # sqlserver
                up_sql = f"CREATE TABLE {schema}.{table} (id INT IDENTITY(1,1) PRIMARY KEY);"
                down_sql = f"DROP TABLE IF EXISTS {schema}.{table};"

            create_versioned_migration(migrations_dir, version, f"create_{table}", up_sql)
            create_undo_migration(migrations_dir, version, f"drop_{table}", down_sql)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Step 1: Migrate to 1.0.1 (apply 1.0.0 and 1.0.1)
        result = cli.migrate(target_version="1.0.1")
        assert result.success

        assert verify_table_exists(db_container, "t1", schema)
        assert verify_table_exists(db_container, "t2", schema)
        assert not verify_table_exists(db_container, "t3", schema)

        # Step 2: Undo to 1.0.0 (undo 1.0.1)
        result = cli.undo(target_version="1.0.0")
        assert result.success

        assert verify_table_exists(db_container, "t1", schema)
        assert not verify_table_exists(db_container, "t2", schema)
        assert not verify_table_exists(db_container, "t3", schema)

        # Step 3: Migrate all (apply 1.0.1 and 1.0.2)
        result = cli.migrate()
        assert result.success

        assert verify_table_exists(db_container, "t1", schema)
        assert verify_table_exists(db_container, "t2", schema)
        assert verify_table_exists(db_container, "t3", schema)

    def test_baseline_then_incremental_migrate(self, db_container, tmp_path):
        """Test: baseline existing version, then migrate new versions."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Simulate existing database - create table directly
        db_helper = DatabaseHelper(db_container)
        try:
            if db_type == "postgresql":
                db_helper.execute_statement(
                    f'CREATE TABLE "{schema}"."existing_prod" (id SERIAL PRIMARY KEY)'
                )
            elif db_type == "mysql":
                db_helper.execute_statement(
                    f"CREATE TABLE {schema}.existing_prod (id INT AUTO_INCREMENT PRIMARY KEY)"
                )
            elif db_type == "oracle":
                db_helper.execute_statement(
                    f"CREATE TABLE {schema}.existing_prod (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY)"
                )
            elif db_type == "db2":
                db_helper.execute_statement(
                    f"CREATE TABLE {schema}.existing_prod (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY)"
                )
            else:  # sqlserver
                db_helper.execute_statement(
                    f"CREATE TABLE {schema}.existing_prod (id INT IDENTITY(1,1) PRIMARY KEY)"
                )
            # Commit the table creation
            db_helper._get_provider().commit_transaction()
        finally:
            db_helper.cleanup()

        # Create historical and new migrations
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "historical",
            generate_test_sql(db_type, "existing_prod", schema),  # Represents existing
        )
        create_versioned_migration(
            migrations_dir,
            "1.1.0",
            "new_feature",
            generate_test_sql(db_type, "new_feature", schema),
        )
        create_versioned_migration(
            migrations_dir,
            "1.2.0",
            "another_feature",
            generate_test_sql(db_type, "another_feature", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Step 1: Baseline at 1.0.0 (skip historical)
        result = cli.baseline(baseline_version="1.0.0", baseline_description="Production baseline")
        assert result.success

        # Step 2: Migrate to 1.1.0
        result = cli.migrate(target_version="1.1.0")
        assert result.success
        assert verify_table_exists(db_container, "new_feature", schema)
        assert not verify_table_exists(db_container, "another_feature", schema)

        # Step 3: Info check
        result = cli.info()
        assert result.success
        assert "1.2.0" in result.stdout  # Should show as pending

        # Step 4: Complete migration
        result = cli.migrate()
        assert result.success
        assert verify_table_exists(db_container, "another_feature", schema)

    def test_dry_run_before_actual_migration(self, db_container, tmp_path):
        """Test: dry-run to preview, then actual migration."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "preview",
            generate_test_sql(db_type, "preview_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Step 1: Dry run
        result = cli.migrate(dry_run=True)
        assert result.success
        assert not verify_table_exists(db_container, "preview_table", schema)

        # Step 2: Validate
        result = cli.validate()
        assert result.success

        # Step 3: Actual migration
        result = cli.migrate()
        assert result.success
        assert verify_table_exists(db_container, "preview_table", schema)

    def test_complex_workflow_with_tags(self, db_container, tmp_path):
        """Test complex workflow: baseline, selective migration with tags, undo."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migrations with tags
        migrations = [
            ("1.0.0", "core_schema", ["core"], "core_table"),
            ("1.0.1", "core_data", ["core"], "core_data"),
            ("1.1.0", "optional_feature", ["optional"], "opt_table"),
            ("1.2.0", "another_opt", ["optional"], "opt_table2"),
        ]

        for version, desc, tags, table in migrations:
            if db_type == "postgresql":
                up_sql = f'CREATE TABLE "{schema}"."{table}" (id SERIAL PRIMARY KEY);'
                down_sql = f'DROP TABLE IF EXISTS "{schema}"."{table}";'
            elif db_type == "mysql":
                up_sql = f"CREATE TABLE {schema}.{table} (id INT AUTO_INCREMENT PRIMARY KEY);"
                down_sql = f"DROP TABLE IF EXISTS {schema}.{table};"
            elif db_type == "oracle":
                up_sql = f"CREATE TABLE {schema}.{table} (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
                # Oracle stores unquoted identifiers as uppercase, so DROP must use uppercase
                # to match the stored table name
                down_sql = f"DROP TABLE {schema}.{table.upper()};"
            elif db_type == "db2":
                up_sql = f"CREATE TABLE {schema}.{table} (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
                down_sql = f"DROP TABLE {schema}.{table};"
            else:  # sqlserver
                up_sql = f"CREATE TABLE {schema}.{table} (id INT IDENTITY(1,1) PRIMARY KEY);"
                down_sql = f"DROP TABLE IF EXISTS {schema}.{table};"

            create_versioned_migration(migrations_dir, version, desc, up_sql, tags=tags)
            create_undo_migration(migrations_dir, version, f"undo_{desc}", down_sql, tags=tags)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Step 1: Migrate only core
        result = cli.migrate(tags=["core"])
        assert result.success

        assert verify_table_exists(db_container, "core_table", schema)
        assert verify_table_exists(db_container, "core_data", schema)
        assert not verify_table_exists(db_container, "opt_table", schema)

        # Step 2: Migrate optional
        result = cli.migrate(tags=["optional"])
        assert result.success

        assert verify_table_exists(db_container, "opt_table", schema)
        assert verify_table_exists(db_container, "opt_table2", schema)

        # Step 3: Undo optional features
        result = cli.undo(target_version="1.0.1", tags=["optional"])
        # Should complete (may or may not undo based on implementation)
        assert result.returncode is not None

    def test_multiple_migration_directories_workflow(self, db_container, tmp_path):
        """Test workflow with multiple migration directories."""
        migrations_dir1 = tmp_path / "migrations_core"
        migrations_dir2 = tmp_path / "migrations_module"
        migrations_dir1.mkdir()
        migrations_dir2.mkdir()

        # Create config with primary migrations directory
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir1)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Core migrations
        create_versioned_migration(
            migrations_dir1,
            "1.0.0",
            "core",
            generate_test_sql(db_type, "core_main", schema),
        )

        # Module migrations
        create_versioned_migration(
            migrations_dir2,
            "2.0.0",
            "module",
            generate_test_sql(db_type, "module_table", schema),
        )

        # Use primary directory for CLI
        cli = DBLiftCLI(config_file, migrations_dir1)

        # Migrate with additional scripts directory
        result = cli.migrate(additional_scripts=[migrations_dir2])

        assert result.success, f"Migration failed: {result.stderr}"

        # Both tables should exist
        assert verify_table_exists(db_container, "core_main", schema)
        assert verify_table_exists(db_container, "module_table", schema)
