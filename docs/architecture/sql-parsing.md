# SQL Parsing System

**Location**: `core/sql_parser/`

Parses SQL scripts to extract statements and handle dialect-specific syntax.

## Overview

The SQL parsing system is responsible for:

- Splitting SQL scripts into individual statements
- Handling dialect-specific delimiters
- Processing comments and special syntax
- Supporting multiple SQL dialects

## Statement Extraction

SQL migration files are split into executable statements:

```python
class SQLParser:
    def parse_statements(self, sql_content: str) -> List[str]:
        """
        Split SQL content into individual statements.
        Handles:
        - Statement terminators (;)
        - Multi-line statements
        - Comments (-- and /* */)
        - Dialect-specific delimiters
        """
```

## Dialect Support

Different databases use different statement terminators and syntax:

- **PostgreSQL/MySQL/SQL Server**: Standard `;` terminator
- **Oracle**: May use `/` for PL/SQL blocks
- **DB2**: Uses `@` for some statements
- **SQLite**: Standard `;` terminator
- **Cosmos DB**: Uses pseudo-SQL (translated to SDK calls)

## Statement Execution

Parsed statements are executed sequentially:

```python
# Migration file content
sql_content = """
CREATE TABLE users (id INT);
INSERT INTO users VALUES (1);
CREATE INDEX idx_users_id ON users(id);
"""

# Parsed into statements
statements = parser.parse_statements(sql_content)
# ['CREATE TABLE users (id INT)', 'INSERT INTO users VALUES (1)', ...]

# Executed one by one
for statement in statements:
    query_executor.execute(connection, statement)
```

## Error Handling

- **Syntax Errors**: Detected during parsing
- **Execution Errors**: Caught during statement execution
- **Transaction Rollback**: Failed statements trigger rollback

## Related Documentation

- **[Migration Engine](migration-engine.md)** - How SQL is executed
- **[Database Providers](database-providers.md)** - Dialect-specific handling
