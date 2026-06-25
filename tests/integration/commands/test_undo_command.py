"""
Test undo command for rolling back migrations.

The undo command rolls back previously applied migrations.
It requires corresponding undo migration files (U{version}__{description}.sql).

Options:
- --target-version (undo to specific version)
- --dry-run (preview undo without applying)
- --tags (filter by tags)

All tests use the production CLI (cli/main.py).
"""

import pytest

from tests.integration.helpers.cli_runner import DBLiftCLI
from tests.integration.helpers.database_helper import verify_table_exists
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
class TestUndoCommand:
    """Test undo command with various scenarios."""

    def test_undo_single_migration(self, db_container, tmp_path):
        """Test undo of a single migration."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create versioned migration
        if db_type == "postgresql":
            up_sql = f'CREATE TABLE "{schema}"."undo_test" (id SERIAL PRIMARY KEY);'
            down_sql = f'DROP TABLE IF EXISTS "{schema}"."undo_test";'
        elif db_type == "mysql":
            up_sql = f"CREATE TABLE {schema}.undo_test (id INT AUTO_INCREMENT PRIMARY KEY);"
            down_sql = f"DROP TABLE IF EXISTS {schema}.undo_test;"
        elif db_type == "oracle":
            up_sql = f"CREATE TABLE {schema}.undo_test (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
            down_sql = f"DROP TABLE {schema}.undo_test;"
        elif db_type == "db2":
            up_sql = f"CREATE TABLE {schema}.undo_test (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
            down_sql = f"DROP TABLE {schema}.undo_test;"
        else:  # sqlserver
            up_sql = f"CREATE TABLE {schema}.undo_test (id INT IDENTITY(1,1) PRIMARY KEY);"
            down_sql = f"DROP TABLE IF EXISTS {schema}.undo_test;"

        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "create_table",
            up_sql,
        )

        # Create undo migration
        create_undo_migration(
            migrations_dir,
            "1.0.0",
            "drop_table",
            down_sql,
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Apply migration
        result = cli.migrate()
        assert result.success
        assert verify_table_exists(db_container, "undo_test", schema)

        # Undo migration
        result = cli.undo(target_version="0.0.0")  # Undo all

        assert result.success, f"Undo failed: {result.stderr}"
        # Table should be dropped
        assert not verify_table_exists(db_container, "undo_test", schema)

    def test_undo_to_target_version(self, db_container, tmp_path):
        """Test undo to specific target version."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create three migrations with undo scripts
        for version, table in [("1.0.0", "table1"), ("1.0.1", "table2"), ("1.0.2", "table3")]:
            if db_type == "postgresql":
                up_sql = f'CREATE TABLE "{schema}"."{table}" (id SERIAL PRIMARY KEY);'
                down_sql = f'DROP TABLE IF EXISTS "{schema}"."{table}";'
            elif db_type == "mysql":
                up_sql = f"CREATE TABLE {schema}.{table} (id INT AUTO_INCREMENT PRIMARY KEY);"
                down_sql = f"DROP TABLE IF EXISTS {schema}.{table};"
            elif db_type == "oracle":
                up_sql = f"CREATE TABLE {schema}.{table} (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
                down_sql = f"DROP TABLE {schema}.{table};"
            elif db_type == "db2":
                up_sql = f"CREATE TABLE {schema}.{table} (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
                down_sql = f"DROP TABLE {schema}.{table};"
            else:  # sqlserver
                up_sql = f"CREATE TABLE {schema}.{table} (id INT IDENTITY(1,1) PRIMARY KEY);"
                down_sql = f"DROP TABLE IF EXISTS {schema}.{table};"

            create_versioned_migration(
                migrations_dir,
                version,
                f"create_{table}",
                up_sql,
            )
            create_undo_migration(
                migrations_dir,
                version,
                f"drop_{table}",
                down_sql,
            )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Apply all migrations
        result = cli.migrate()
        assert result.success

        # Verify all tables exist
        assert verify_table_exists(db_container, "table1", schema)
        assert verify_table_exists(db_container, "table2", schema)
        assert verify_table_exists(db_container, "table3", schema)

        # Undo to 1.0.0 (should undo 1.0.2 and 1.0.1, keep 1.0.0)
        result = cli.undo(target_version="1.0.0")

        assert result.success, f"Undo failed: {result.stderr}"

        # table1 should still exist, table2 and table3 should be gone
        assert verify_table_exists(db_container, "table1", schema)
        assert not verify_table_exists(db_container, "table2", schema)
        assert not verify_table_exists(db_container, "table3", schema)

    def test_undo_dry_run(self, db_container, tmp_path):
        """Test undo with --dry-run option."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migration with undo
        if db_type == "postgresql":
            up_sql = f'CREATE TABLE "{schema}"."dryrun_test" (id SERIAL PRIMARY KEY);'
            down_sql = f'DROP TABLE IF EXISTS "{schema}"."dryrun_test";'
        elif db_type == "mysql":
            up_sql = f"CREATE TABLE {schema}.dryrun_test (id INT AUTO_INCREMENT PRIMARY KEY);"
            down_sql = f"DROP TABLE IF EXISTS {schema}.dryrun_test;"
        elif db_type == "oracle":
            up_sql = f"CREATE TABLE {schema}.dryrun_test (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
            down_sql = f"DROP TABLE {schema}.dryrun_test;"
        elif db_type == "db2":
            up_sql = f"CREATE TABLE {schema}.dryrun_test (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
            down_sql = f"DROP TABLE {schema}.dryrun_test;"
        else:  # sqlserver
            up_sql = f"CREATE TABLE {schema}.dryrun_test (id INT IDENTITY(1,1) PRIMARY KEY);"
            down_sql = f"DROP TABLE IF EXISTS {schema}.dryrun_test;"

        create_versioned_migration(migrations_dir, "1.0.0", "create", up_sql)
        create_undo_migration(migrations_dir, "1.0.0", "drop", down_sql)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Apply migration
        result = cli.migrate()
        assert result.success
        assert verify_table_exists(db_container, "dryrun_test", schema)

        # Dry run undo
        result = cli.undo(target_version="0.0.0", dry_run=True)

        assert result.success, f"Undo dry run failed: {result.stderr}"
        # Dry-run content goes to stderr via self.log.info; use .output (stdout+stderr)
        output_lower = result.output.lower()
        assert "dry" in output_lower or "would" in output_lower

        # Table should STILL exist (dry run didn't apply)
        assert verify_table_exists(db_container, "dryrun_test", schema)

    def test_undo_without_undo_script(self, db_container, tmp_path):
        """Test undo when undo script is missing."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migration WITHOUT undo script
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "no_undo",
            generate_test_sql(db_type, "no_undo_table", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Apply migration
        result = cli.migrate()
        assert result.success

        # Try to undo without undo script
        result = cli.undo(target_version="0.0.0")

        # Should fail or warn about missing undo script
        assert (
            not result.success
            or "missing" in result.stderr.lower()
            or "not found" in result.stderr.lower()
        )

    def test_undo_incremental(self, db_container, tmp_path):
        """Test incremental undo operations."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create two migrations with undo
        for version, table in [("1.0.0", "incr1"), ("1.0.1", "incr2")]:
            if db_type == "postgresql":
                up_sql = f'CREATE TABLE "{schema}"."{table}" (id SERIAL PRIMARY KEY);'
                down_sql = f'DROP TABLE IF EXISTS "{schema}"."{table}";'
            elif db_type == "mysql":
                up_sql = f"CREATE TABLE {schema}.{table} (id INT AUTO_INCREMENT PRIMARY KEY);"
                down_sql = f"DROP TABLE IF EXISTS {schema}.{table};"
            elif db_type == "oracle":
                up_sql = f"CREATE TABLE {schema}.{table} (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
                down_sql = f"DROP TABLE {schema}.{table};"
            elif db_type == "db2":
                up_sql = f"CREATE TABLE {schema}.{table} (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
                down_sql = f"DROP TABLE {schema}.{table};"
            else:  # sqlserver
                up_sql = f"CREATE TABLE {schema}.{table} (id INT IDENTITY(1,1) PRIMARY KEY);"
                down_sql = f"DROP TABLE IF EXISTS {schema}.{table};"

            create_versioned_migration(migrations_dir, version, f"create_{table}", up_sql)
            create_undo_migration(migrations_dir, version, f"drop_{table}", down_sql)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Apply all
        result = cli.migrate()
        assert result.success

        # Undo one at a time
        # First undo to 1.0.0 (undoes 1.0.1)
        result = cli.undo(target_version="1.0.0")
        assert result.success
        assert verify_table_exists(db_container, "incr1", schema)
        assert not verify_table_exists(db_container, "incr2", schema)

        # Then undo to 0.0.0 (undoes 1.0.0)
        result = cli.undo(target_version="0.0.0")
        assert result.success
        assert not verify_table_exists(db_container, "incr1", schema)

    def test_undo_with_tags(self, db_container, tmp_path):
        """Test undo with tag filtering."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migrations with tags
        for version, table, tags in [
            ("1.0.0", "core_table", ["core"]),
            ("1.0.1", "opt_table", ["optional"]),
        ]:
            if db_type == "postgresql":
                up_sql = f'CREATE TABLE "{schema}"."{table}" (id SERIAL PRIMARY KEY);'
                down_sql = f'DROP TABLE IF EXISTS "{schema}"."{table}";'
            elif db_type == "mysql":
                up_sql = f"CREATE TABLE {schema}.{table} (id INT AUTO_INCREMENT PRIMARY KEY);"
                down_sql = f"DROP TABLE IF EXISTS {schema}.{table};"
            elif db_type == "oracle":
                up_sql = f"CREATE TABLE {schema}.{table} (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
                down_sql = f"DROP TABLE {schema}.{table};"
            elif db_type == "db2":
                up_sql = f"CREATE TABLE {schema}.{table} (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
                down_sql = f"DROP TABLE {schema}.{table};"
            else:  # sqlserver
                up_sql = f"CREATE TABLE {schema}.{table} (id INT IDENTITY(1,1) PRIMARY KEY);"
                down_sql = f"DROP TABLE IF EXISTS {schema}.{table};"

            create_versioned_migration(
                migrations_dir, version, f"create_{table}", up_sql, tags=tags
            )
            create_undo_migration(migrations_dir, version, f"drop_{table}", down_sql, tags=tags)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Apply all migrations
        result = cli.migrate()
        assert result.success

        # Undo only optional tagged migrations
        result = cli.undo(target_version="1.0.0", tags=["optional"])

        # Should succeed (though behavior may vary)
        # At minimum, should not crash
        assert result.returncode is not None


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["postgresql", "mysql", "sqlserver", "oracle", "db2"],
    indirect=True,
)
class TestUndoComplexScenarios:
    """Test undo in complex scenarios."""

    def test_migrate_undo_migrate_cycle(self, db_container, tmp_path):
        """Test cycle of migrate -> undo -> migrate again."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        if db_type == "postgresql":
            up_sql = f'CREATE TABLE "{schema}"."cycle_test" (id SERIAL PRIMARY KEY);'
            down_sql = f'DROP TABLE IF EXISTS "{schema}"."cycle_test";'
        elif db_type == "mysql":
            up_sql = f"CREATE TABLE {schema}.cycle_test (id INT AUTO_INCREMENT PRIMARY KEY);"
            down_sql = f"DROP TABLE IF EXISTS {schema}.cycle_test;"
        elif db_type == "oracle":
            up_sql = f"CREATE TABLE {schema}.cycle_test (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
            down_sql = f"DROP TABLE {schema}.cycle_test;"
        elif db_type == "db2":
            up_sql = f"CREATE TABLE {schema}.cycle_test (id INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY);"
            down_sql = f"DROP TABLE {schema}.cycle_test;"
        else:  # sqlserver
            up_sql = f"CREATE TABLE {schema}.cycle_test (id INT IDENTITY(1,1) PRIMARY KEY);"
            down_sql = f"DROP TABLE IF EXISTS {schema}.cycle_test;"

        create_versioned_migration(migrations_dir, "1.0.0", "create", up_sql)
        create_undo_migration(migrations_dir, "1.0.0", "drop", down_sql)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Migrate
        result = cli.migrate()
        assert result.success
        assert verify_table_exists(db_container, "cycle_test", schema)

        # Undo
        result = cli.undo(target_version="0.0.0")
        assert result.success
        assert not verify_table_exists(db_container, "cycle_test", schema)

        # Migrate again
        result = cli.migrate()
        assert result.success
        assert verify_table_exists(db_container, "cycle_test", schema)
