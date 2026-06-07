-- Add audit fields to existing tables
-- This migration adds tracking fields for auditing purposes

-- Add audit fields to users table
ALTER TABLE users 
ADD COLUMN created_by VARCHAR(50) DEFAULT 'system',
ADD COLUMN updated_by VARCHAR(50) DEFAULT 'system',
ADD COLUMN is_deleted BOOLEAN DEFAULT false,
ADD COLUMN deleted_at TIMESTAMP,
ADD COLUMN deleted_by VARCHAR(50);

-- Add audit fields to products table
ALTER TABLE products 
ADD COLUMN created_by VARCHAR(50) DEFAULT 'system',
ADD COLUMN updated_by VARCHAR(50) DEFAULT 'system',
ADD COLUMN is_deleted BOOLEAN DEFAULT false,
ADD COLUMN deleted_at TIMESTAMP,
ADD COLUMN deleted_by VARCHAR(50);

-- Add audit fields to orders table
ALTER TABLE orders 
ADD COLUMN created_by VARCHAR(50) DEFAULT 'system',
ADD COLUMN updated_by VARCHAR(50) DEFAULT 'system';

-- Create audit trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for automatic updated_at updates
CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_products_updated_at BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create indexes for audit fields
CREATE INDEX idx_users_deleted ON users(is_deleted);
CREATE INDEX idx_products_deleted ON products(is_deleted);

COMMENT ON FUNCTION update_updated_at_column() IS 'Automatically updates updated_at timestamp';