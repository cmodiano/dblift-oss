#!/bin/bash

# Script to set up DBLift environment

# Create directories if they don't exist
mkdir -p logs
mkdir -p migrations

# Create a sample configuration file if it doesn't exist
if [ ! -f "dblift.yaml" ]; then
    echo "Creating sample configuration file..."
    cat > dblift.yaml << EOF
# DBLift Configuration

database:
  type: sqlserver  # or oracle
  server: localhost
  port: 1433  # for SQL Server (use 1521 for Oracle)
  database_name: mydatabase
  schema: dbo  # for SQL Server (use your schema name for Oracle)
  username: username
  password: password

migrations_dir: migrations
log_format: text  # text, json, or html
log_level: INFO   # DEBUG, INFO, WARNING, ERROR
EOF
    echo "Sample configuration file created: dblift.yaml"
fi

# Create a sample migration if migrations directory is empty
if [ -z "$(ls -A migrations 2>/dev/null)" ]; then
    echo "Creating sample migration..."
    cat > migrations/V1_0_0__Initial_schema.sql << EOF
-- Sample migration script
-- Create a simple table

CREATE TABLE sample_table (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    created_date DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Insert some initial data
INSERT INTO sample_table (id, name) VALUES (1, 'Sample Data');
EOF
    echo "Sample migration created: migrations/V1_0_0__Initial_schema.sql"
fi

echo "DBLift environment setup complete!"
echo "To run DBLift, use: python -m dblift [command]"
echo "For example: python -m dblift info --config dblift.yaml" 
