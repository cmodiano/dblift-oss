# Database Providers Reference

Database provider implementations for each supported database.

## Base Provider

::: db.base_provider
    options:
      show_root_heading: true
      show_source: true

## Provider Architecture

Each database provider implements a common interface through 5 specialized components:

1. **ConnectionManager** - Creates and configures database connections
2. **QueryExecutor** - Executes SQL statements
3. **SchemaOperations** - Schema DDL operations
4. **LockingManager** - Migration locking mechanism
5. **HistoryManager** - Migration history tracking

See the [Database Providers Architecture](../architecture/database-providers.md) for detailed information.

## Supported Databases

- **PostgreSQL** (`db.plugins.postgresql`) - Native SQLAlchemy provider
- **MySQL** (`db.plugins.mysql`) - Native SQLAlchemy provider
- **SQL Server** (`db.plugins.sqlserver`) - Native SQLAlchemy provider
- **Oracle** (`db.plugins.oracle`) - Native SQLAlchemy provider
- **DB2** (`db.plugins.db2`) - Native SQLAlchemy provider
- **SQLite** (`db.plugins.sqlite`) - Python native provider
- **Cosmos DB** (`db.plugins.cosmosdb`) - Azure SDK provider

## Component Interfaces

All providers implement these base interfaces:

- `db.base_connection_manager.BaseConnectionManager`
- `db.base_query_executor.BaseQueryExecutor`
- `db.base_schema_operations.BaseSchemaOperations`
- `db.base_locking_manager.BaseLockingManager`
- `db.base_history_manager.BaseHistoryManager`

For implementation details, see the source code in `db/plugins/<database>/`.
