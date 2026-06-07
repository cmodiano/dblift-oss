-- Add products table
-- This migration adds product management functionality

-- Create products table
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    category VARCHAR(50),
    stock_quantity INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create products indexes
CREATE INDEX idx_products_name ON products(name);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_active ON products(is_active);

-- Add some sample products
INSERT INTO products (name, description, price, category, stock_quantity) VALUES
('Widget A', 'A useful widget for various purposes', 19.99, 'widgets', 100),
('Gadget B', 'An innovative gadget with multiple features', 49.99, 'gadgets', 50),
('Tool C', 'Professional tool for advanced users', 99.99, 'tools', 25);

COMMENT ON TABLE products IS 'Product catalog table';