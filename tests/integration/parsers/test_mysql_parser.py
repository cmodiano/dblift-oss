"""
Test MySQL SQL parsing through CLI.

CRITICAL: These tests verify that the MySQL parser correctly handles
complex MySQL scripts including:
- DELIMITER changes for stored procedures
- Stored procedures and functions
- Triggers
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
class TestMySQLParser:
    """Test MySQL SQL parsing through CLI."""

    def test_delimiter_change_basic(self, mysql_container, tmp_path):
        """Test basic DELIMITER change for stored procedures."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE orders (
            id INT AUTO_INCREMENT PRIMARY KEY,
            total DECIMAL(10, 2)
        );

        DELIMITER $$

        CREATE PROCEDURE calculate_order_total(
            IN order_id INT,
            OUT order_total DECIMAL(10, 2)
        )
        BEGIN
            DECLARE item_total DECIMAL(10, 2);
            
            SELECT SUM(price * quantity) INTO item_total
            FROM order_items
            WHERE order_id = order_id;
            
            SET order_total = item_total * 1.1;
        END$$

        DELIMITER ;

        INSERT INTO orders (total) VALUES (100.00);
        """

        create_migration(migrations_dir, "V1_0_0__procedures.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Migration failed: {result.stderr}"
        assert verify_table_exists(mysql_container, "orders")

    def test_multiple_delimiters(self, mysql_container, tmp_path):
        """Test multiple DELIMITER changes in one script."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE products (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100),
            price DECIMAL(10, 2)
        );

        DELIMITER $$

        CREATE PROCEDURE add_product(
            IN p_name VARCHAR(100),
            IN p_price DECIMAL(10, 2)
        )
        BEGIN
            INSERT INTO products (name, price) VALUES (p_name, p_price);
        END$$

        DELIMITER ;

        INSERT INTO products (name, price) VALUES ('Widget', 19.99);

        DELIMITER //

        CREATE FUNCTION get_product_count() RETURNS INT
        DETERMINISTIC
        BEGIN
            DECLARE product_count INT;
            SELECT COUNT(*) INTO product_count FROM products;
            RETURN product_count;
        END//

        DELIMITER ;
        """

        create_migration(migrations_dir, "V1_0_0__multi_delim.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(mysql_container, "products")

    def test_trigger_with_delimiter(self, mysql_container, tmp_path):
        """Test trigger creation with DELIMITER."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE audit_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            table_name VARCHAR(100),
            operation VARCHAR(10),
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100),
            email VARCHAR(255)
        );

        DELIMITER $$

        CREATE TRIGGER users_audit_trigger
        AFTER INSERT ON users
        FOR EACH ROW
        BEGIN
            INSERT INTO audit_log (table_name, operation)
            VALUES ('users', 'INSERT');
        END$$

        DELIMITER ;
        """

        create_migration(migrations_dir, "V1_0_0__trigger.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(mysql_container, "users")
        assert verify_table_exists(mysql_container, "audit_log")

    def test_nested_begin_end_blocks(self, mysql_container, tmp_path):
        """Test nested BEGIN/END blocks in procedures."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE accounts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            balance DECIMAL(10, 2)
        );

        DELIMITER $$

        CREATE PROCEDURE transfer_funds(
            IN from_account INT,
            IN to_account INT,
            IN amount DECIMAL(10, 2)
        )
        BEGIN
            DECLARE from_balance DECIMAL(10, 2);
            
            -- Outer BEGIN/END
            START TRANSACTION;
            
            -- Get source balance
            SELECT balance INTO from_balance
            FROM accounts
            WHERE id = from_account
            FOR UPDATE;
            
            -- Inner block with condition
            IF from_balance >= amount THEN
                BEGIN
                    UPDATE accounts SET balance = balance - amount
                    WHERE id = from_account;
                    
                    UPDATE accounts SET balance = balance + amount
                    WHERE id = to_account;
                    
                    COMMIT;
                END;
            ELSE
                ROLLBACK;
            END IF;
        END$$

        DELIMITER ;

        INSERT INTO accounts (balance) VALUES (1000.00), (500.00);
        """

        create_migration(migrations_dir, "V1_0_0__nested.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_string_literals_with_semicolons(self, mysql_container, tmp_path):
        """Test string literals containing semicolons."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            text TEXT
        );

        -- String with semicolon
        INSERT INTO messages (text) VALUES ('This has a semicolon; but should not split');

        -- String with quotes
        INSERT INTO messages (text) VALUES ('This has \\'quoted\\' text');

        -- String in procedure
        DELIMITER $$
        CREATE PROCEDURE log_message(IN msg TEXT)
        BEGIN
            INSERT INTO messages (text) VALUES (CONCAT('Log: ', msg, '; done'));
        END$$
        DELIMITER ;
        """

        create_migration(migrations_dir, "V1_0_0__strings.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_comments_various_styles(self, mysql_container, tmp_path):
        """Test various MySQL comment styles."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        -- Single line comment
        CREATE TABLE test1 (id INT PRIMARY KEY);

        # MySQL hash comment
        CREATE TABLE test2 (id INT PRIMARY KEY);

        /* Multi-line comment
           with multiple lines
           and semicolons; in it
        */
        CREATE TABLE test3 (id INT PRIMARY KEY);

        DELIMITER $$
        CREATE PROCEDURE test_proc()
        BEGIN
            -- Comment inside procedure
            SELECT 1;
            # Another comment style
            /* Multi-line
               inside procedure */
            SELECT 2;
        END$$
        DELIMITER ;
        """

        create_migration(migrations_dir, "V1_0_0__comments.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_delimiter_in_comments_and_strings(self, mysql_container, tmp_path):
        """Test that DELIMITER in comments/strings doesn't change delimiter."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE config (
            id INT AUTO_INCREMENT PRIMARY KEY,
            value TEXT
        );

        -- This comment has DELIMITER in it (shouldn't affect parsing)
        INSERT INTO config (value) VALUES ('DELIMITER is a keyword');

        /* Multi-line with DELIMITER $$
           DELIMITER ;
           (these shouldn't change delimiter)
        */
        INSERT INTO config (value) VALUES ('test');

        DELIMITER $$

        CREATE PROCEDURE real_delimiter()
        BEGIN
            -- Now we're using $$ as delimiter
            INSERT INTO config (value) VALUES ('procedure with $$');
        END$$

        DELIMITER ;
        """

        create_migration(migrations_dir, "V1_0_0__delim_test.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_stored_function_with_return(self, mysql_container, tmp_path):
        """Test stored function with RETURNS clause."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE employees (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(100),
            salary DECIMAL(10, 2)
        );

        DELIMITER $$

        CREATE FUNCTION calculate_bonus(emp_id INT) RETURNS DECIMAL(10, 2)
        DETERMINISTIC
        BEGIN
            DECLARE emp_salary DECIMAL(10, 2);
            DECLARE bonus DECIMAL(10, 2);
            
            SELECT salary INTO emp_salary
            FROM employees
            WHERE id = emp_id;
            
            IF emp_salary > 50000 THEN
                SET bonus = emp_salary * 0.10;
            ELSE
                SET bonus = emp_salary * 0.05;
            END IF;
            
            RETURN bonus;
        END$$

        DELIMITER ;

        INSERT INTO employees (name, salary) VALUES ('John Doe', 60000.00);
        """

        create_migration(migrations_dir, "V1_0_0__function.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_complex_case_statement(self, mysql_container, tmp_path):
        """Test complex CASE statements in procedures."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE order_status (
            id INT AUTO_INCREMENT PRIMARY KEY,
            status VARCHAR(50)
        );

        DELIMITER $$

        CREATE PROCEDURE update_order_status(
            IN order_id INT,
            IN new_status VARCHAR(50)
        )
        BEGIN
            DECLARE status_code INT;
            
            -- CASE statement with multiple conditions
            SET status_code = CASE new_status
                WHEN 'pending' THEN 1
                WHEN 'processing' THEN 2
                WHEN 'shipped' THEN 3
                WHEN 'delivered' THEN 4
                ELSE 0
            END;
            
            IF status_code > 0 THEN
                INSERT INTO order_status (status) VALUES (new_status);
            END IF;
        END$$

        DELIMITER ;
        """

        create_migration(migrations_dir, "V1_0_0__case.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_multiple_triggers_same_table(self, mysql_container, tmp_path):
        """Test multiple triggers on the same table."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE inventory (
            id INT AUTO_INCREMENT PRIMARY KEY,
            product_name VARCHAR(100),
            quantity INT
        );

        CREATE TABLE inventory_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            action VARCHAR(50),
            log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        DELIMITER $$

        CREATE TRIGGER inventory_after_insert
        AFTER INSERT ON inventory
        FOR EACH ROW
        BEGIN
            INSERT INTO inventory_log (action)
            VALUES (CONCAT('Added: ', NEW.product_name));
        END$$

        CREATE TRIGGER inventory_after_update
        AFTER UPDATE ON inventory
        FOR EACH ROW
        BEGIN
            INSERT INTO inventory_log (action)
            VALUES (CONCAT('Updated: ', NEW.product_name));
        END$$

        CREATE TRIGGER inventory_after_delete
        AFTER DELETE ON inventory
        FOR EACH ROW
        BEGIN
            INSERT INTO inventory_log (action)
            VALUES (CONCAT('Deleted: ', OLD.product_name));
        END$$

        DELIMITER ;
        """

        create_migration(migrations_dir, "V1_0_0__multi_triggers.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"

    def test_event_creation(self, mysql_container, tmp_path):
        """Test MySQL event (scheduled task) creation."""
        migrations_dir = tmp_path / "migrations"

        migrations_dir.mkdir()

        config_file = create_config(tmp_path, mysql_container, migrations_dir=migrations_dir)

        sql_script = """
        CREATE TABLE event_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            event_name VARCHAR(100),
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE cleanup_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            cleanup_date DATE
        );

        -- Enable event scheduler (usually enabled by default)
        SET GLOBAL event_scheduler = ON;

        -- Create event that runs every 5 minutes
        DELIMITER $$
        CREATE EVENT log_event
        ON SCHEDULE EVERY 5 MINUTE
        STARTS CURRENT_TIMESTAMP
        DO
        BEGIN
            INSERT INTO event_log (event_name) VALUES ('periodic_log');
        END$$
        DELIMITER ;

        -- Create event that runs once
        DELIMITER $$
        CREATE EVENT one_time_cleanup
        ON SCHEDULE AT CURRENT_TIMESTAMP + INTERVAL 1 DAY
        DO
        BEGIN
            INSERT INTO cleanup_log (cleanup_date) VALUES (CURDATE());
            DELETE FROM event_log WHERE executed_at < DATE_SUB(NOW(), INTERVAL 30 DAY);
        END$$
        DELIMITER ;

        -- Create disabled event
        CREATE EVENT disabled_event
        ON SCHEDULE EVERY 1 HOUR
        DISABLE
        DO
            INSERT INTO event_log (event_name) VALUES ('disabled');

        -- Initial data
        INSERT INTO event_log (event_name) VALUES ('initial');
        """

        create_migration(migrations_dir, "V1_0_0__events.sql", sql_script)

        cli = DBLiftCLI(config_file, migrations_dir)
        result = cli.migrate()

        assert result.success, f"Failed: {result.stderr}"
        assert verify_table_exists(mysql_container, "event_log")
        assert verify_table_exists(mysql_container, "cleanup_log")
