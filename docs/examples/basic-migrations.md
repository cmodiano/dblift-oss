# Basic Migration Examples

Common migration patterns and examples.

## Creating Tables

### Simple Table

```sql
-- V1_0_0__create_users_table.sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Table with Foreign Key

```sql
-- V1_0_1__create_orders_table.sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

## Adding Columns

```sql
-- V1_0_2__add_phone_to_users.sql
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
ALTER TABLE users ADD COLUMN phone_verified BOOLEAN DEFAULT FALSE;
```

## Creating Indexes

```sql
-- V1_0_3__add_user_indexes.sql
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE UNIQUE INDEX idx_users_phone ON users(phone) WHERE phone IS NOT NULL;
```

## Creating Views

```sql
-- R__user_summary_view.sql
CREATE OR REPLACE VIEW user_summary AS
SELECT 
    u.id,
    u.username,
    u.email,
    COUNT(o.id) as order_count,
    SUM(o.total_amount) as total_spent
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.username, u.email;
```

## Data Migrations

```sql
-- V1_0_4__migrate_user_data.sql
-- Update existing users with default values
UPDATE users 
SET phone_verified = FALSE 
WHERE phone_verified IS NULL;

-- Migrate data from old column to new column
UPDATE users 
SET email = old_email 
WHERE email IS NULL AND old_email IS NOT NULL;
```

## Undo Migrations

```sql
-- U1_0_2__remove_phone_from_users.sql
ALTER TABLE users DROP COLUMN phone_verified;
ALTER TABLE users DROP COLUMN phone;
```

## Next Steps

- See [Advanced Scenarios](advanced-scenarios.md) for complex examples
- Review [Best Practices](../user-guide/best-practices.md)
- Check [Commands Reference](../user-guide/commands.md)
