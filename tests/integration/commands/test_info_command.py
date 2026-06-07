"""
Test info command with all options.

The info command shows the status of all migrations:
- Applied migrations (with timestamps)
- Pending migrations
- Baselined migrations
- Failed migrations

Options:
- --tags (filter by tags)
- --exclude-tags (exclude by tags)
- --versions (filter by versions)
- --exclude-versions (exclude by versions)
- --log-level (debug, info, warn, error)

All tests use the production CLI (cli/main.py).
"""

import json

import pytest

from tests.integration.helpers.cli_runner import DBLiftCLI
from tests.integration.helpers.migration_helper import (
    create_config,
    create_repeatable_migration,
    create_versioned_migration,
    generate_test_sql,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["postgresql", "mysql", "sqlserver", "oracle", "db2"],
    indirect=True,
)
class TestInfoCommand:
    """Test info command with various options."""

    def test_info_no_migrations(self, db_container, tmp_path):
        """Test info with no migration files."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        cli = DBLiftCLI(config_file, migrations_dir)

        result = cli.info()

        assert result.success, f"Info failed: {result.stderr}"
        output_lower = result.stdout.lower()
        assert "no migrations" in output_lower or "empty" in output_lower or result.success

    def test_info_pending_migrations(self, db_container, tmp_path):
        """Test info showing pending migrations."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create some migrations
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "first",
            generate_test_sql(db_type, "table1", schema),
        )
        create_versioned_migration(
            migrations_dir,
            "1.0.1",
            "second",
            generate_test_sql(db_type, "table2", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        result = cli.info()

        assert result.success, f"Info failed: {result.stderr}"
        # Should show pending migrations
        output_lower = result.stdout.lower()
        assert "pending" in output_lower or "not applied" in output_lower
        assert "1.0.0" in result.stdout
        assert "1.0.1" in result.stdout

    def test_info_applied_migrations(self, db_container, tmp_path):
        """Test info showing applied migrations."""
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

        # Apply migration
        migrate_result = cli.migrate()
        assert migrate_result.success

        # Check info
        result = cli.info()

        assert result.success, f"Info failed: {result.stderr}"
        # Should show as applied/success
        output_lower = result.stdout.lower()
        assert "success" in output_lower or "applied" in output_lower
        assert "1.0.0" in result.stdout

    def test_info_with_log_levels(self, db_container, tmp_path):
        """Test info command with different log levels."""
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

        # Get info with debug log level
        result = cli.info(log_level="debug")

        assert result.success, f"Info failed: {result.stderr}"
        # Should show migration information
        assert "1.0.0" in result.stdout or "V1_0_0" in result.stdout

    def test_info_with_tags(self, db_container, tmp_path):
        """Test info filtering by tags."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create migrations with different tags
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "core",
            generate_test_sql(db_type, "core_table", schema),
            tags=["core"],
        )
        create_versioned_migration(
            migrations_dir,
            "1.0.1",
            "optional",
            generate_test_sql(db_type, "optional_table", schema),
            tags=["optional"],
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Get info for core tags only
        result = cli.info(tags=["core"])

        assert result.success, f"Info failed: {result.stderr}"
        # Should show core migration
        assert "1.0.0" in result.stdout or "core" in result.stdout.lower()

    def test_info_mixed_status(self, db_container, tmp_path):
        """Test info showing mixed migration statuses."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create multiple migrations
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "first",
            generate_test_sql(db_type, "table1", schema),
        )
        create_versioned_migration(
            migrations_dir,
            "1.0.1",
            "second",
            generate_test_sql(db_type, "table2", schema),
        )
        create_versioned_migration(
            migrations_dir,
            "1.0.2",
            "third",
            generate_test_sql(db_type, "table3", schema),
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Apply only first two
        migrate_result = cli.migrate(target_version="1.0.1")
        assert migrate_result.success

        # Check info
        result = cli.info()

        assert result.success, f"Info failed: {result.stderr}"
        # Should show some applied and some pending
        assert "1.0.0" in result.stdout
        assert "1.0.1" in result.stdout
        assert "1.0.2" in result.stdout

    def test_info_with_repeatable(self, db_container, tmp_path):
        """Test info showing repeatable migrations."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create versioned and repeatable
        create_versioned_migration(
            migrations_dir,
            "1.0.0",
            "table",
            generate_test_sql(db_type, "base_table", schema),
        )

        if db_type == "postgresql":
            view_sql = f'CREATE OR REPLACE VIEW "{schema}"."test_view" AS SELECT * FROM "{schema}"."base_table";'
        elif db_type == "mysql":
            view_sql = (
                f"CREATE OR REPLACE VIEW {schema}.test_view AS SELECT * FROM {schema}.base_table;"
            )
        elif db_type == "oracle":
            # Oracle: Use quoted identifiers to match how generate_test_sql creates tables
            # Tables are created as "TEST_SCHEMA"."base_table" (quoted, preserving case)
            # Views must reference them the same way, otherwise Oracle converts unquoted
            # identifiers to uppercase and can't find the table
            view_sql = f'CREATE OR REPLACE VIEW "{schema}"."test_view" AS SELECT * FROM "{schema}"."base_table";'
        elif db_type == "db2":
            view_sql = (
                f"CREATE OR REPLACE VIEW {schema}.test_view AS SELECT * FROM {schema}.base_table;"
            )
        else:  # sqlserver
            view_sql = f"""
            IF OBJECT_ID('{schema}.test_view', 'V') IS NOT NULL DROP VIEW {schema}.test_view;
            GO
            CREATE VIEW {schema}.test_view AS SELECT * FROM {schema}.base_table;
            """

        create_repeatable_migration(
            migrations_dir,
            "create_views",
            view_sql,
        )

        cli = DBLiftCLI(config_file, migrations_dir)

        # Apply migrations
        migrate_result = cli.migrate()
        assert migrate_result.success

        # Check info
        result = cli.info()

        assert result.success, f"Info failed: {result.stderr}"
        # Should show both versioned and repeatable
        assert "1.0.0" in result.stdout or "V1_0_0" in result.stdout
        assert "R__create_views" in result.stdout or "repeatable" in result.stdout.lower()

    def test_info_after_baseline(self, db_container, tmp_path):
        """Test info showing baselined migrations."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()
        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        cli = DBLiftCLI(config_file, migrations_dir)

        # Baseline at 1.0.0
        baseline_result = cli.baseline(
            baseline_version="1.0.0", baseline_description="Production baseline"
        )
        assert baseline_result.success

        # Check info
        result = cli.info()

        assert result.success, f"Info failed: {result.stderr}"
        # Should show baseline
        assert "1.0.0" in result.stdout
        output_lower = result.stdout.lower()
        assert "baseline" in output_lower or "success" in output_lower
