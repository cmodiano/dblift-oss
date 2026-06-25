# Advanced Migration Scenarios

Complex migration patterns and real-world examples.

## Multi-Step Migrations

Break complex changes into multiple migrations:

```sql
-- V1_0_0__create_users_table.sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL
);

-- V1_0_1__add_user_email.sql
ALTER TABLE users ADD COLUMN email VARCHAR(255);
CREATE INDEX idx_users_email ON users(email);

-- V1_0_2__add_user_phone.sql
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
ALTER TABLE users ADD COLUMN phone_verified BOOLEAN DEFAULT FALSE;
```

## Conditional Migrations

Handle different database states:

```sql
-- V1_0_3__add_column_if_not_exists.sql
-- PostgreSQL example
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'middle_name'
    ) THEN
        ALTER TABLE users ADD COLUMN middle_name VARCHAR(100);
    END IF;
END $$;
```

## Schema Migrations

```sql
-- V1_0_4__create_custom_schema.sql
CREATE SCHEMA IF NOT EXISTS reporting;
CREATE TABLE reporting.monthly_reports (
    id SERIAL PRIMARY KEY,
    report_date DATE NOT NULL,
    data JSONB
);
```

## Stored Procedures

```sql
-- R__calculate_user_stats.sql
CREATE OR REPLACE FUNCTION calculate_user_stats(user_id INTEGER)
RETURNS TABLE (
    total_orders INTEGER,
    total_spent DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(o.id)::INTEGER as total_orders,
        COALESCE(SUM(o.total_amount), 0) as total_spent
    FROM orders o
    WHERE o.user_id = calculate_user_stats.user_id;
END;
$$ LANGUAGE plpgsql;
```

## Partitioned Tables

```sql
-- V1_0_5__create_partitioned_orders.sql
-- PostgreSQL example
CREATE TABLE orders (
    id SERIAL,
    user_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    total_amount DECIMAL(10, 2)
) PARTITION BY RANGE (order_date);

CREATE TABLE orders_2024_q1 PARTITION OF orders
    FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');

CREATE TABLE orders_2024_q2 PARTITION OF orders
    FOR VALUES FROM ('2024-04-01') TO ('2024-07-01');
```

## Tagged Migrations

Organize migrations by feature:

```sql
-- V1_0_0__create_users[core,init].sql
CREATE TABLE users (...);

-- V1_0_1__create_auth_tables[auth].sql
CREATE TABLE sessions (...);

-- V2_0_0__create_billing[billing].sql
CREATE TABLE invoices (...);
```

Deploy specific features:
```bash
dblift migrate --tags=auth
dblift migrate --exclude-tags=billing
```

## Complex Data Migrations

```sql
-- V1_0_6__migrate_user_roles.sql
-- Step 1: Create new table
CREATE TABLE user_roles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    role VARCHAR(50) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Step 2: Migrate data
INSERT INTO user_roles (user_id, role)
SELECT id, 'user' FROM users WHERE role IS NULL;

-- Step 3: Update existing data
INSERT INTO user_roles (user_id, role)
SELECT id, role FROM users WHERE role IS NOT NULL;

-- Step 4: Drop old column (in separate migration)
-- V1_0_7__drop_old_role_column.sql
ALTER TABLE users DROP COLUMN role;
```

## Zero-Downtime Migrations

```sql
-- V1_0_8__add_column_zero_downtime.sql
-- Step 1: Add nullable column
ALTER TABLE users ADD COLUMN new_field VARCHAR(255);

-- Step 2: Backfill data (can be done in batches)
UPDATE users SET new_field = old_field WHERE new_field IS NULL;

-- Step 3: Make column NOT NULL (separate migration after backfill)
-- V1_0_9__make_column_not_null.sql
ALTER TABLE users ALTER COLUMN new_field SET NOT NULL;
```

## Next Steps

- Review [Basic Migrations](basic-migrations.md) for simple examples
- See [Best Practices](../user-guide/best-practices.md)
- Check [Commands Reference](../user-guide/commands.md)
