"""
Test tag-based migration filtering through CLI.

CRITICAL: These tests verify that tag filtering works correctly:
- --tags: Include only migrations with specific tags
- --exclude-tags: Exclude migrations with specific tags
- Multiple tags (comma-separated)
- Migrations without tags
- Complex tag scenarios

All tests use the production CLI (cli/main.py) to ensure
tag filtering works end-to-end in real migrations.
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
class TestTags:
    """Test tag-based migration filtering through CLI."""

    def test_single_tag_filter(self, postgresql_container, tmp_path):
        """Test filtering migrations by a single tag."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create migrations with different tags
        create_migration(
            migrations_dir,
            "V1_0_0__users[ddl].sql",
            "CREATE TABLE users (id SERIAL PRIMARY KEY, username VARCHAR(100));",
        )

        create_migration(
            migrations_dir,
            "V1_0_1__user_data[dml].sql",
            "INSERT INTO users (username) VALUES ('admin');",
        )

        create_migration(
            migrations_dir,
            "V1_0_2__products[ddl].sql",
            "CREATE TABLE products (id SERIAL PRIMARY KEY, name VARCHAR(100));",
        )

        # Migrate with --tags ddl (should only run V1_0_0 and V1_0_2)
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(tags="ddl")

        assert result.success, f"Failed: {result.stderr}"

        # Verify only DDL migrations ran
        assert verify_table_exists(postgresql_container, "users")
        assert verify_table_exists(postgresql_container, "products")

        # The DML migration should not have run (but table exists, so can't check data easily)
        # Better to check via info command or migration history

    def test_multiple_tags_filter(self, postgresql_container, tmp_path):
        """Test filtering migrations by multiple tags."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create migrations with different tags
        create_migration(
            migrations_dir,
            "V1_0_0__schema[ddl,core].sql",
            "CREATE SCHEMA IF NOT EXISTS app_schema;",
        )

        create_migration(
            migrations_dir,
            "V1_0_1__users[ddl,users].sql",
            "CREATE TABLE users (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_2__data[dml,users].sql",
            "CREATE TABLE user_data (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_3__products[ddl,products].sql",
            "CREATE TABLE products (id SERIAL PRIMARY KEY);",
        )

        # Migrate with --tags ddl,users (should run V1_0_0, V1_0_1, V1_0_2)
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(tags="ddl,users")

        assert result.success, f"Failed: {result.stderr}"

        assert verify_table_exists(postgresql_container, "users")
        assert verify_table_exists(postgresql_container, "user_data")

    def test_exclude_tags(self, postgresql_container, tmp_path):
        """Test excluding migrations by tags."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create migrations
        create_migration(
            migrations_dir,
            "V1_0_0__users[stable].sql",
            "CREATE TABLE users (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_1__orders[experimental].sql",
            "CREATE TABLE orders (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_2__products[stable].sql",
            "CREATE TABLE products (id SERIAL PRIMARY KEY);",
        )

        # Migrate with --exclude-tags experimental
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(exclude_tags="experimental")

        assert result.success, f"Failed: {result.stderr}"

        # Stable migrations should run
        assert verify_table_exists(postgresql_container, "users")
        assert verify_table_exists(postgresql_container, "products")

        # Experimental migration should not run
        assert not verify_table_exists(postgresql_container, "orders")

    def test_exclude_multiple_tags(self, postgresql_container, tmp_path):
        """Test excluding multiple tags."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__base[core].sql", "CREATE TABLE base (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir,
            "V1_0_1__experimental[experimental,beta].sql",
            "CREATE TABLE experimental (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_2__beta[beta].sql",
            "CREATE TABLE beta_table (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_3__stable[stable].sql",
            "CREATE TABLE stable (id SERIAL PRIMARY KEY);",
        )

        # Exclude experimental and beta tags
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(exclude_tags="experimental,beta")

        assert result.success, f"Failed: {result.stderr}"

        assert verify_table_exists(postgresql_container, "base")
        assert verify_table_exists(postgresql_container, "stable")
        assert not verify_table_exists(postgresql_container, "experimental")
        assert not verify_table_exists(postgresql_container, "beta_table")

    def test_tags_and_exclude_tags_together(self, postgresql_container, tmp_path):
        """Test using both --tags and --exclude-tags together."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir,
            "V1_0_0__schema[ddl,core].sql",
            "CREATE TABLE t1 (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_1__users[ddl,experimental].sql",
            "CREATE TABLE t2 (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_2__products[ddl,stable].sql",
            "CREATE TABLE t3 (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_3__data[dml,stable].sql",
            "CREATE TABLE t4 (id SERIAL PRIMARY KEY);",
        )

        # Include ddl but exclude experimental
        # Should run V1_0_0 and V1_0_2 (ddl + not experimental)
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(tags="ddl", exclude_tags="experimental")

        assert result.success, f"Failed: {result.stderr}"

        assert verify_table_exists(postgresql_container, "t1")  # ddl,core
        assert not verify_table_exists(postgresql_container, "t2")  # ddl,experimental (excluded)
        assert verify_table_exists(postgresql_container, "t3")  # ddl,stable
        assert not verify_table_exists(postgresql_container, "t4")  # dml,stable (not ddl)

    def test_migration_without_tags(self, postgresql_container, tmp_path):
        """Test migrations without tags are included by default."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Migration without tags
        create_migration(
            migrations_dir, "V1_0_0__no_tags.sql", "CREATE TABLE no_tags (id SERIAL PRIMARY KEY);"
        )

        # Migration with tags
        create_migration(
            migrations_dir,
            "V1_0_1__with_tags[tagged].sql",
            "CREATE TABLE with_tags (id SERIAL PRIMARY KEY);",
        )

        # Migrate without tag filters - both should run
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(postgresql_container, "no_tags")
        assert verify_table_exists(postgresql_container, "with_tags")

    def test_tag_filter_no_matches(self, postgresql_container, tmp_path):
        """Test tag filter with no matching migrations."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__users[ddl].sql", "CREATE TABLE users (id SERIAL PRIMARY KEY);"
        )

        # Filter by non-existent tag
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(tags="nonexistent")

        # Should succeed but apply no migrations
        assert result.success, f"Failed: {result.stderr}"
        # No tables should be created
        # (Hard to verify without checking history table)

    def test_tags_with_repeatable_migrations(self, postgresql_container, tmp_path):
        """Test tag filtering with repeatable migrations."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Versioned with tag
        create_migration(
            migrations_dir, "V1_0_0__base[ddl].sql", "CREATE TABLE base (id SERIAL PRIMARY KEY);"
        )

        # Repeatable with tag
        create_migration(
            migrations_dir, "R__view[ddl].sql", "CREATE OR REPLACE VIEW test_view AS SELECT 1;"
        )

        # Repeatable without tag
        create_migration(
            migrations_dir,
            "R__procedure.sql",
            "CREATE OR REPLACE FUNCTION test_func() RETURNS INT AS $$ BEGIN RETURN 1; END; $$ LANGUAGE plpgsql;",
        )

        # Migrate with ddl tag - should run versioned and repeatable with ddl tag
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(tags="ddl")

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(postgresql_container, "base")

    def test_tags_with_undo(self, postgresql_container, tmp_path):
        """Test that tags work with undo migrations."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Create forward and undo migrations with tags
        create_migration(
            migrations_dir, "V1_0_0__users[ddl].sql", "CREATE TABLE users (id SERIAL PRIMARY KEY);"
        )

        create_migration(migrations_dir, "U1_0_0__users[ddl].sql", "DROP TABLE users;")

        create_migration(
            migrations_dir,
            "V1_0_1__products[dml].sql",
            "CREATE TABLE products (id SERIAL PRIMARY KEY);",
        )

        create_migration(migrations_dir, "U1_0_1__products[dml].sql", "DROP TABLE products;")

        # Apply all migrations
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()
        assert result.success, f"Failed: {result.stderr}"

        # Undo with ddl tag filter - should only undo users
        result = cli.undo(tags="ddl")
        assert result.success, f"Failed: {result.stderr}"

        # Users should be undone, products should remain
        assert not verify_table_exists(postgresql_container, "users")
        assert verify_table_exists(postgresql_container, "products")

    def test_tags_with_dry_run(self, postgresql_container, tmp_path):
        """Test tag filtering works with dry-run."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__users[ddl].sql", "CREATE TABLE users (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir,
            "V1_0_1__data[dml].sql",
            "CREATE TABLE user_data (id SERIAL PRIMARY KEY);",
        )

        # Dry run with tag filter
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(tags="ddl", dry_run=True)

        assert result.success, f"Failed: {result.stderr}"

        # No tables should exist (dry run)
        assert not verify_table_exists(postgresql_container, "users")
        assert not verify_table_exists(postgresql_container, "user_data")

    def test_complex_tag_scenario(self, postgresql_container, tmp_path):
        """Test complex real-world tag scenario."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        # Environment-based tags
        create_migration(
            migrations_dir,
            "V1_0_0__core_schema[core,prod,dev].sql",
            "CREATE TABLE core_table (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_1__dev_data[dev,test_data].sql",
            "CREATE TABLE dev_table (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_2__prod_config[prod,config].sql",
            "CREATE TABLE prod_config (id SERIAL PRIMARY KEY);",
        )

        create_migration(
            migrations_dir,
            "V1_0_3__test_fixtures[test_data].sql",
            "CREATE TABLE test_fixtures (id SERIAL PRIMARY KEY);",
        )

        # Simulate production deployment: include prod, exclude test_data
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate(tags="prod", exclude_tags="test_data")

        assert result.success, f"Failed: {result.stderr}"

        assert verify_table_exists(postgresql_container, "core_table")  # core,prod,dev
        assert not verify_table_exists(
            postgresql_container, "dev_table"
        )  # dev,test_data (excluded)
        assert verify_table_exists(postgresql_container, "prod_config")  # prod,config
        assert not verify_table_exists(
            postgresql_container, "test_fixtures"
        )  # test_data (excluded)

    def test_info_command_with_tags(self, postgresql_container, tmp_path):
        """Test that info command respects tag filters."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, postgresql_container, migrations_dir=migrations_dir)

        create_migration(
            migrations_dir, "V1_0_0__users[ddl].sql", "CREATE TABLE users (id SERIAL PRIMARY KEY);"
        )

        create_migration(
            migrations_dir,
            "V1_0_1__data[dml].sql",
            "CREATE TABLE user_data (id SERIAL PRIMARY KEY);",
        )

        # Get info with tag filter
        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.info(tags="ddl")

        assert result.success, f"Failed: {result.stderr}"
        # Info should show filtered migrations
        # (Output parsing would be needed for thorough validation)
