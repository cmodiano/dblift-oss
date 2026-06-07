-- Undo script for V1_1_0__Add_audit_fields.sql
-- This script removes the audit fields and triggers that were added

-- Drop triggers first
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
DROP TRIGGER IF EXISTS update_products_updated_at ON products;
DROP TRIGGER IF EXISTS update_orders_updated_at ON orders;

-- Drop the trigger function
DROP FUNCTION IF EXISTS update_updated_at_column();

-- Remove audit indexes
DROP INDEX IF EXISTS idx_users_deleted;
DROP INDEX IF EXISTS idx_products_deleted;

-- Remove audit fields from orders table
ALTER TABLE orders 
DROP COLUMN IF EXISTS created_by,
DROP COLUMN IF EXISTS updated_by;

-- Remove audit fields from products table
ALTER TABLE products 
DROP COLUMN IF EXISTS created_by,
DROP COLUMN IF EXISTS updated_by,
DROP COLUMN IF EXISTS is_deleted,
DROP COLUMN IF EXISTS deleted_at,
DROP COLUMN IF EXISTS deleted_by;

-- Remove audit fields from users table
ALTER TABLE users 
DROP COLUMN IF EXISTS created_by,
DROP COLUMN IF EXISTS updated_by,
DROP COLUMN IF EXISTS is_deleted,
DROP COLUMN IF EXISTS deleted_at,
DROP COLUMN IF EXISTS deleted_by;