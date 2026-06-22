"""
Test DB2 SQL parsing through CLI.

CRITICAL: These tests verify that the DB2 parser correctly handles
complex DB2 scripts including:
- Statement terminators (semicolon and @)
- Stored procedures with compound SQL
- Triggers
- Functions
- Multiple statement terminators in one script
- String literals with special characters
- Comments

All tests use the production CLI (cli/main.py) to ensure
parsing works end-to-end in real migrations.
"""

import pytest

from tests.integration.helpers.cli_runner_direct import DBLiftCLIDirect as DBLiftCLI
from tests.integration.helpers.database_helper import verify_table_exists
from tests.integration.helpers.migration_helper import (
    create_config,
    create_migration,
)


@pytest.mark.integration
class TestDB2Parser:
    """Test DB2 SQL parsing through CLI."""

    def test_at_delimiter_basic(self, db2_container, tmp_path):
        """Test basic @ delimiter for DB2 procedures."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            emp_id INT NOT NULL PRIMARY KEY,
            emp_name VARCHAR(100),
            salary DECIMAL(10, 2)
        )@

        CREATE PROCEDURE add_employee(
            IN p_id INT,
            IN p_name VARCHAR(100),
            IN p_salary DECIMAL(10, 2)
        )
        LANGUAGE SQL
        BEGIN
            INSERT INTO employees (emp_id, emp_name, salary)
            VALUES (p_id, p_name, p_salary);
        END@

        INSERT INTO employees VALUES (1, 'John Doe', 50000.00)@
        """

        create_migration(migrations_dir, "V1_0_0__procedures.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Migration failed: {result.stderr}"
        assert verify_table_exists(db2_container, "employees")

    def test_semicolon_delimiter(self, db2_container, tmp_path):
        """Test semicolon delimiter for regular SQL."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE test1 (id INT NOT NULL PRIMARY KEY);
        CREATE TABLE test2 (id INT NOT NULL PRIMARY KEY);
        CREATE TABLE test3 (id INT NOT NULL PRIMARY KEY);

        INSERT INTO test1 VALUES (1);
        INSERT INTO test2 VALUES (2);
        INSERT INTO test3 VALUES (3);
        """

        create_migration(migrations_dir, "V1_0_0__simple.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_mixed_delimiters(self, db2_container, tmp_path):
        """Test mixing semicolon and @ delimiters."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        -- Regular SQL with semicolons
        CREATE TABLE products (
            product_id INT NOT NULL PRIMARY KEY,
            product_name VARCHAR(100),
            price DECIMAL(10, 2)
        );

        INSERT INTO products VALUES (1, 'Widget', 19.99);

        -- Procedure with @ delimiter
        CREATE PROCEDURE calculate_total()
        LANGUAGE SQL
        DYNAMIC RESULT SETS 1
        BEGIN
            DECLARE total_cursor CURSOR WITH RETURN FOR
                SELECT SUM(price) as total FROM products;
            
            OPEN total_cursor;
        END@

        -- Back to semicolon
        INSERT INTO products VALUES (2, 'Gadget', 29.99);
        """

        create_migration(migrations_dir, "V1_0_0__mixed.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_trigger_with_compound_sql(self, db2_container, tmp_path):
        """Test trigger with compound SQL statement."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE audit_log (
            log_id INT NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            table_name VARCHAR(100),
            operation VARCHAR(10),
            log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE users (
            user_id INT NOT NULL PRIMARY KEY,
            username VARCHAR(100)
        );

        CREATE TRIGGER users_audit_trigger
        AFTER INSERT ON users
        REFERENCING NEW AS n
        FOR EACH ROW
        BEGIN ATOMIC
            INSERT INTO audit_log (table_name, operation)
            VALUES ('users', 'INSERT');
        END@
        """

        create_migration(migrations_dir, "V1_0_0__trigger.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_nested_compound_sql(self, db2_container, tmp_path):
        """Test nested compound SQL blocks."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE accounts (
            account_id INT NOT NULL PRIMARY KEY,
            balance DECIMAL(10, 2)
        );

        CREATE PROCEDURE transfer_funds(
            IN p_from_account INT,
            IN p_to_account INT,
            IN p_amount DECIMAL(10, 2)
        )
        LANGUAGE SQL
        BEGIN
            DECLARE v_balance DECIMAL(10, 2);
            
            -- Get source balance
            SELECT balance INTO v_balance
            FROM accounts
            WHERE account_id = p_from_account;
            
            -- Nested condition
            IF v_balance >= p_amount THEN
                BEGIN
                    UPDATE accounts
                    SET balance = balance - p_amount
                    WHERE account_id = p_from_account;
                    
                    UPDATE accounts
                    SET balance = balance + p_amount
                    WHERE account_id = p_to_account;
                END;
            END IF;
        END@

        INSERT INTO accounts VALUES (1, 1000.00);
        INSERT INTO accounts VALUES (2, 500.00);
        """

        create_migration(migrations_dir, "V1_0_0__nested.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_procedure_with_multiple_out_params(self, db2_container, tmp_path):
        """Test DB2 procedure with multiple OUT parameters and @ delimiter."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE orders (
            order_id INT NOT NULL PRIMARY KEY,
            subtotal DECIMAL(10, 2),
            tax DECIMAL(10, 2),
            total DECIMAL(10, 2)
        );

        CREATE PROCEDURE calculate_order_totals(
            IN p_subtotal DECIMAL(10, 2),
            OUT p_tax DECIMAL(10, 2),
            OUT p_total DECIMAL(10, 2)
        )
        LANGUAGE SQL
        BEGIN
            SET p_tax = p_subtotal * 0.08;
            SET p_total = p_subtotal + p_tax;
        END@

        INSERT INTO orders VALUES (1, 100.00, 8.00, 108.00);
        """

        create_migration(migrations_dir, "V1_0_0__proc_out.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_string_literals_with_quotes(self, db2_container, tmp_path):
        """Test string literals with special characters."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE messages (
            id INT NOT NULL PRIMARY KEY,
            text VARCHAR(1000)
        );

        -- String with embedded quote (escaped as '')
        INSERT INTO messages VALUES (1, 'This has a ''quoted'' word');

        -- String with @ symbol (shouldn't be treated as delimiter)
        INSERT INTO messages VALUES (2, 'Email: user@example.com');

        -- Procedure with string containing special chars
        CREATE PROCEDURE log_message(IN p_msg VARCHAR(1000))
        LANGUAGE SQL
        BEGIN
            INSERT INTO messages VALUES (3, 'Log: ' || p_msg || '; done');
        END@
        """

        create_migration(migrations_dir, "V1_0_0__strings.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_comments_various_styles(self, db2_container, tmp_path):
        """Test various DB2 comment styles."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        -- Single line comment
        CREATE TABLE test1 (id INT NOT NULL PRIMARY KEY);

        /* Multi-line comment
           with multiple lines
           and special chars @;
        */
        CREATE TABLE test2 (id INT NOT NULL PRIMARY KEY);

        CREATE PROCEDURE test_proc()
        LANGUAGE SQL
        BEGIN
            -- Comment inside procedure
            DECLARE v_count INT;
            /* Multi-line
               inside procedure */
            SET v_count = 1;
        END@
        """

        create_migration(migrations_dir, "V1_0_0__comments.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_case_expression(self, db2_container, tmp_path):
        """Test CASE expressions in procedures."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE order_status (
            status_id INT NOT NULL PRIMARY KEY,
            status_name VARCHAR(50)
        );

        CREATE PROCEDURE update_status(IN p_status_code INT)
        LANGUAGE SQL
        BEGIN
            DECLARE v_status_name VARCHAR(50);
            
            SET v_status_name = CASE p_status_code
                WHEN 1 THEN 'Pending'
                WHEN 2 THEN 'Processing'
                WHEN 3 THEN 'Shipped'
                WHEN 4 THEN 'Delivered'
                ELSE 'Unknown'
            END;
            
            INSERT INTO order_status VALUES (p_status_code, v_status_name);
        END@
        """

        create_migration(migrations_dir, "V1_0_0__case.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_dynamic_result_sets(self, db2_container, tmp_path):
        """Test procedure with dynamic result sets."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE departments (
            dept_id INT NOT NULL PRIMARY KEY,
            dept_name VARCHAR(100)
        );

        CREATE PROCEDURE get_departments()
        LANGUAGE SQL
        DYNAMIC RESULT SETS 1
        BEGIN
            DECLARE dept_cursor CURSOR WITH RETURN FOR
                SELECT dept_id, dept_name
                FROM departments
                ORDER BY dept_id;
            
            OPEN dept_cursor;
        END@

        INSERT INTO departments VALUES (1, 'Engineering');
        INSERT INTO departments VALUES (2, 'Sales');
        """

        create_migration(migrations_dir, "V1_0_0__cursor.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_signal_condition(self, db2_container, tmp_path):
        """Test SIGNAL statement for error handling."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE inventory (
            item_id INT NOT NULL PRIMARY KEY,
            quantity INT
        );

        CREATE PROCEDURE check_stock(IN p_item_id INT)
        LANGUAGE SQL
        BEGIN
            DECLARE v_quantity INT;
            
            SELECT quantity INTO v_quantity
            FROM inventory
            WHERE item_id = p_item_id;
            
            IF v_quantity < 10 THEN
                SIGNAL SQLSTATE '75001'
                    SET MESSAGE_TEXT = 'Low stock warning';
            END IF;
        END@

        INSERT INTO inventory VALUES (1, 5);
        """

        create_migration(migrations_dir, "V1_0_0__signal.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_multiple_triggers_same_table(self, db2_container, tmp_path):
        """Test multiple triggers on the same table."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE inventory (
            id INT NOT NULL PRIMARY KEY,
            product_name VARCHAR(100),
            quantity INT
        );

        CREATE TABLE inventory_log (
            log_id INT NOT NULL GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            action VARCHAR(50),
            log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TRIGGER inventory_after_insert
        AFTER INSERT ON inventory
        REFERENCING NEW AS n
        FOR EACH ROW
        BEGIN ATOMIC
            INSERT INTO inventory_log (action)
            VALUES ('Added: ' || n.product_name);
        END@

        CREATE TRIGGER inventory_after_update
        AFTER UPDATE ON inventory
        REFERENCING NEW AS n
        FOR EACH ROW
        BEGIN ATOMIC
            INSERT INTO inventory_log (action)
            VALUES ('Updated: ' || n.product_name);
        END@
        """

        create_migration(migrations_dir, "V1_0_0__multi_triggers.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    @pytest.mark.skip(
        reason="CREATE OR REPLACE MODULE requires DB2 11.1+ not available in test environment"
    )
    def test_module_creation(self, db2_container, tmp_path):
        """Test DB2 module creation (similar to Oracle packages) - SKIPPED."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            emp_id INT NOT NULL PRIMARY KEY,
            emp_name VARCHAR(100),
            salary DECIMAL(10, 2)
        );

        -- Create a module with procedures and functions
        CREATE OR REPLACE MODULE hr_module
            -- Module procedures
            PROCEDURE add_employee(
                IN p_id INT,
                IN p_name VARCHAR(100),
                IN p_salary DECIMAL(10, 2)
            )
            LANGUAGE SQL
            BEGIN
                INSERT INTO employees (emp_id, emp_name, salary)
                VALUES (p_id, p_name, p_salary);
            END;

            -- Module function
            FUNCTION get_employee_count()
            RETURNS INT
            LANGUAGE SQL
            BEGIN
                DECLARE v_count INT;
                SELECT COUNT(*) INTO v_count FROM employees;
                RETURN v_count;
            END;

            -- Another procedure
            PROCEDURE update_salary(
                IN p_emp_id INT,
                IN p_new_salary DECIMAL(10, 2)
            )
            LANGUAGE SQL
            BEGIN
                UPDATE employees
                SET salary = p_new_salary
                WHERE emp_id = p_emp_id;
            END;
        END MODULE@

        -- Insert test data
        INSERT INTO employees VALUES (1, 'John Doe', 50000.00);
        INSERT INTO employees VALUES (2, 'Jane Smith', 60000.00);
        """

        create_migration(migrations_dir, "V1_0_0__module.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(db2_container, "employees")

    @pytest.mark.skip(
        reason="CREATE OR REPLACE MODULE requires DB2 11.1+ not available in test environment"
    )
    def test_module_with_published_routines(self, db2_container, tmp_path):
        """Test DB2 module with published (public) and non-published routines - SKIPPED."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, db2_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE orders (
            order_id INT NOT NULL PRIMARY KEY,
            total DECIMAL(10, 2)
        );

        -- Module with both public and internal routines
        CREATE OR REPLACE MODULE order_module
            -- Published procedure (accessible outside module)
            PUBLISH PROCEDURE process_order(IN p_order_id INT)
            LANGUAGE SQL
            BEGIN
                CALL internal_validate_order(p_order_id);
                CALL internal_update_status(p_order_id);
            END;

            -- Internal procedure (only accessible within module)
            PROCEDURE internal_validate_order(IN p_order_id INT)
            LANGUAGE SQL
            BEGIN
                DECLARE v_total DECIMAL(10, 2);
                SELECT total INTO v_total
                FROM orders
                WHERE order_id = p_order_id;
                
                IF v_total <= 0 THEN
                    SIGNAL SQLSTATE '75001'
                        SET MESSAGE_TEXT = 'Invalid order total';
                END IF;
            END;

            -- Internal procedure
            PROCEDURE internal_update_status(IN p_order_id INT)
            LANGUAGE SQL
            BEGIN
                -- Update order status logic here
                NULL;
            END;
        END MODULE@

        INSERT INTO orders VALUES (1, 100.50);
        """

        create_migration(migrations_dir, "V1_0_0__module_published.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(db2_container, "orders")
