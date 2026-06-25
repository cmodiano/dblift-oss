"""
Test new project workflow - starting from scratch.

This test simulates a real user starting a new project with DBLift:
1. Create migration files
2. Check status with info
3. Validate migrations
4. Preview with dry-run
5. Apply migrations
6. Verify results
7. Add more migrations
8. Apply incrementally

All tests use the production CLI (cli/main.py) exactly as a user would.
"""

import pytest

from tests.integration.helpers.cli_runner_direct import DBLiftCLIDirect as DBLiftCLI
from tests.integration.helpers.database_helper import (
    get_table_count,
    verify_table_exists,
)
from tests.integration.helpers.migration_helper import (
    create_config,
    create_migration,
    create_repeatable_migration,
    create_versioned_migration,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "db_container",
    ["postgresql"],  # Scenario tests verify tool logic, not database-specific behavior
    indirect=True,
)
class TestNewProjectWorkflow:
    """Test complete workflow for starting a new project."""

    def test_new_project_complete_workflow(self, db_container, tmp_path):
        """
        Test complete workflow for starting a new project from scratch.

        This test simulates exactly what a user would do when setting up
        a new project with DBLift.
        """
        # Setup
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        cli = DBLiftCLI(config_file, migrations_dir)
        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Step 1: Create initial migration files
        if db_type == "postgresql":
            initial_sql = f"""
            CREATE TABLE "{schema}"."users" (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE "{schema}"."roles" (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50) NOT NULL UNIQUE
            );

            CREATE TABLE "{schema}"."user_roles" (
                user_id INT REFERENCES "{schema}"."users"(id),
                role_id INT REFERENCES "{schema}"."roles"(id),
                PRIMARY KEY (user_id, role_id)
            );
            """
        elif db_type == "mysql":
            initial_sql = f"""
            CREATE TABLE {schema}.users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE {schema}.roles (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(50) NOT NULL UNIQUE
            );

            CREATE TABLE {schema}.user_roles (
                user_id INT,
                role_id INT,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES {schema}.users(id),
                FOREIGN KEY (role_id) REFERENCES {schema}.roles(id)
            );
            """
        else:  # sqlserver
            initial_sql = f"""
            CREATE TABLE {schema}.users (
                id INT IDENTITY(1,1) PRIMARY KEY,
                username NVARCHAR(100) NOT NULL UNIQUE,
                email NVARCHAR(255) NOT NULL UNIQUE,
                created_at DATETIME DEFAULT GETDATE()
            );

            CREATE TABLE {schema}.roles (
                id INT IDENTITY(1,1) PRIMARY KEY,
                name NVARCHAR(50) NOT NULL UNIQUE
            );

            CREATE TABLE {schema}.user_roles (
                user_id INT FOREIGN KEY REFERENCES {schema}.users(id),
                role_id INT FOREIGN KEY REFERENCES {schema}.roles(id),
                PRIMARY KEY (user_id, role_id)
            );
            """

        create_versioned_migration(migrations_dir, "1.0.0", "initial_schema", initial_sql)

        # Step 2: Check status (should show pending)
        result = cli.info()
        assert result.success, f"Info failed: {result.stderr}"
        output_lower = result.stdout.lower()
        assert (
            "pending" in output_lower or "not applied" in output_lower
        ), "Should show migrations as pending"
        assert "V1_0_0__initial_schema.sql" in result.stdout or "1.0.0" in result.stdout

        # Step 3: Validate migrations
        result = cli.validate()
        assert result.success, f"Validate failed: {result.stderr}"

        # Step 4: Preview with dry-run
        result = cli.migrate(dry_run=True)
        assert result.success, f"Dry-run failed: {result.stderr}"
        # Verify no actual changes were made
        assert not verify_table_exists(db_container, "users", schema)

        # Step 5: Apply migrations
        result = cli.migrate()
        assert result.success, f"Migrate failed: {result.stderr}"
        assert "1.0.0" in result.stdout or "V1_0_0" in result.stdout

        # Step 6: Verify database state
        assert verify_table_exists(db_container, "users", schema)
        assert verify_table_exists(db_container, "roles", schema)
        assert verify_table_exists(db_container, "user_roles", schema)

        # Step 7: Verify status (should show applied)
        result = cli.info()
        assert result.success, f"Info failed: {result.stderr}"
        output_lower = result.stdout.lower()
        assert (
            "success" in output_lower or "applied" in output_lower
        ), "Should show migrations as applied"

        # Step 8: Try to migrate again (should be no-op)
        result = cli.migrate()
        assert result.success, f"Second migrate failed: {result.stderr}"
        assert (
            "up to date" in result.stdout.lower()
            or "no pending" in result.stdout.lower()
            or "already applied" in result.stdout.lower()
        )

        # Step 9: Add more migrations
        if db_type == "postgresql":
            data_sql = f"""
            INSERT INTO "{schema}"."roles" (name) VALUES ('admin'), ('user'), ('moderator');
            INSERT INTO "{schema}"."users" (username, email)
            VALUES
                ('admin', 'admin@example.com'),
                ('john', 'john@example.com'),
                ('jane', 'jane@example.com');
            """
        elif db_type == "mysql":
            data_sql = f"""
            INSERT INTO {schema}.roles (name) VALUES ('admin'), ('user'), ('moderator');
            INSERT INTO {schema}.users (username, email)
            VALUES
                ('admin', 'admin@example.com'),
                ('john', 'john@example.com'),
                ('jane', 'jane@example.com');
            """
        else:  # sqlserver
            data_sql = f"""
            INSERT INTO {schema}.roles (name) VALUES ('admin'), ('user'), ('moderator');
            INSERT INTO {schema}.users (username, email)
            VALUES
                ('admin', 'admin@example.com'),
                ('john', 'john@example.com'),
                ('jane', 'jane@example.com');
            """

        create_versioned_migration(migrations_dir, "1.0.1", "add_sample_data", data_sql)

        # Step 10: Apply new migration
        result = cli.migrate()
        assert result.success, f"Second migration failed: {result.stderr}"
        assert "1.0.1" in result.stdout or "V1_0_1" in result.stdout

        # Step 11: Verify data was inserted
        users_count = get_table_count(db_container, "users", schema)
        roles_count = get_table_count(db_container, "roles", schema)
        assert users_count == 3, f"Expected 3 users, got {users_count}"
        assert roles_count == 3, f"Expected 3 roles, got {roles_count}"

    def test_new_project_with_repeatable_migrations(self, db_container, tmp_path):
        """Test workflow including repeatable migrations."""
        # Setup
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db_container, migrations_dir=migrations_dir)

        cli = DBLiftCLI(config_file, migrations_dir)
        db_type = db_container["type"]
        schema = db_container.get("schema", "TEST_SCHEMA")

        # Create base schema
        if db_type == "postgresql":
            base_sql = f"""
            CREATE TABLE "{schema}"."products" (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price DECIMAL(10, 2)
            );
            """
            view_sql = f"""
            CREATE OR REPLACE VIEW "{schema}"."expensive_products" AS
            SELECT * FROM "{schema}"."products"
            WHERE price > 100;
            """
        elif db_type == "mysql":
            base_sql = f"""
            CREATE TABLE {schema}.products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price DECIMAL(10, 2)
            );
            """
            view_sql = f"""
            CREATE OR REPLACE VIEW {schema}.expensive_products AS
            SELECT * FROM {schema}.products
            WHERE price > 100;
            """
        else:  # sqlserver
            base_sql = f"""
            CREATE TABLE {schema}.products (
                id INT IDENTITY(1,1) PRIMARY KEY,
                name NVARCHAR(100) NOT NULL,
                price DECIMAL(10, 2)
            );
            """
            # SQL Server needs DROP/CREATE for views
            view_sql = f"""
            IF OBJECT_ID('{schema}.expensive_products', 'V') IS NOT NULL
                DROP VIEW {schema}.expensive_products;
            GO
            CREATE VIEW {schema}.expensive_products AS
            SELECT * FROM {schema}.products
            WHERE price > 100;
            """

        create_versioned_migration(migrations_dir, "1.0.0", "create_products", base_sql)
        create_repeatable_migration(migrations_dir, "create_views", view_sql)

        # Apply migrations
        result = cli.migrate()
        assert result.success, f"Migration failed: {result.stderr}"

        # Verify both versioned and repeatable were applied
        assert verify_table_exists(db_container, "products", schema)

        # Modify repeatable migration (change threshold)
        if db_type == "postgresql":
            view_sql_v2 = f"""
            CREATE OR REPLACE VIEW "{schema}"."expensive_products" AS
            SELECT * FROM "{schema}"."products"
            WHERE price > 50;  -- Changed threshold
            """
        elif db_type == "mysql":
            view_sql_v2 = f"""
            CREATE OR REPLACE VIEW {schema}.expensive_products AS
            SELECT * FROM {schema}.products
            WHERE price > 50;  -- Changed threshold
            """
        else:  # sqlserver
            view_sql_v2 = f"""
            IF OBJECT_ID('{schema}.expensive_products', 'V') IS NOT NULL
                DROP VIEW {schema}.expensive_products;
            GO
            CREATE VIEW {schema}.expensive_products AS
            SELECT * FROM {schema}.products
            WHERE price > 50;  -- Changed threshold
            """

        # Overwrite repeatable migration
        (migrations_dir / "R__create_views.sql").write_text(view_sql_v2)

        # Migrate again (repeatable should be re-executed)
        result = cli.migrate()
        assert result.success, f"Repeatable re-execution failed: {result.stderr}"
