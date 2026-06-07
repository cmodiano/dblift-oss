# DBLift Architecture Documentation

**Technical Reference for Developers**

This document describes the current architecture of DBLift - a database migration tool supporting PostgreSQL, MySQL, SQL Server, Oracle, DB2, SQLite, and Azure Cosmos DB. It focuses on how the system is structured today and how components interact.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Layer Architecture](#layer-architecture)
3. [API Client Layer](#api-client-layer)
4. [Migration Engine](#migration-engine)
5. [Database Provider System](#database-provider-system)
6. [Configuration System](#configuration-system)
7. [SQL Parsing System](#sql-parsing-system)
8. [Schema Management](#schema-management)
9. [Schema Validation & Quality Assurance](#schema-validation--quality-assurance)
10. [Connection & Transaction Management](#connection--transaction-management)
11. [Testing Architecture](#testing-architecture)
12. [Adding New Database Support](#adding-new-database-support)

---

## System Overview

### High-Level Architecture

DBLift follows a layered architecture where each layer has clear responsibilities:

```
┌─────────────────────────────────────────────────────────┐
│                     CLI Layer                           │
│                  (cli/main.py)                          │
│  - Argument parsing                                     │
│  - Command routing                                      │
│  - Output formatting                                    │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                  API Client Layer                       │
│                  (api/client.py)                        │
│  - DBLiftClient: High-level operations API              │
│  - Configuration loading                                │
│  - Provider instantiation                               │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                 Migration Engine                        │
│            (core/migration/executor/)                   │
│  - MigrationExecutor: Orchestrates operations           │
│  - Commands: migrate, undo, baseline, diff, etc.        │
│  - State management                                     │
│  - Script management                                    │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│             Database Provider Layer                     │
│                 (db/plugins/)                           │
│  - BaseProvider: Abstract interface                     │
│  - 5 components per database:                           │
│    • ConnectionManager                                  │
│    • QueryExecutor                                      │
│    • SchemaOperations                                   │
│    • LockingManager                                     │
│    • HistoryManager                                     │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│              Database Layer                             │
│  SQLAlchemy: PostgreSQL, MySQL, SQL Server, Oracle, DB2 │
│  Native: SQLite (Python sqlite3)                        │
│  SDK:  Azure Cosmos DB                                  │
└─────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Explicit Ownership**: Provider owns connection, passes it to components as parameters
2. **Stateless Components**: QueryExecutor, SchemaOperations, etc. store no connection state
3. **Dependency Injection**: Dependencies passed explicitly through call chain
4. **Database Abstraction**: Common interface for all database types
5. **Factory Pattern**: Centralized creation of dialect-specific components

---

## Layer Architecture

### Layer Responsibilities

| Layer | Location | Purpose | Key Components |
|-------|----------|---------|----------------|
| **CLI** | `cli/` | User interaction, command parsing | `main.py`, command handlers |
| **API Client** | `api/` | Public API, configuration, provider setup | `DBLiftClient` |
| **Migration Engine** | `core/migration/` | Migration orchestration | `MigrationExecutor`, Commands |
| **Database Providers** | `db/plugins/` | Database-specific operations | Provider implementations |
| **SQL Parsing** | `core/sql_parser/` | SQL dialect parsing | Parser implementations |
| **Configuration** | `config/` | Settings management | `DbliftConfig` |

### Data Flow

**Example: Running a Migration**

```
1. User runs: dblift migrate

2. CLI Layer (cli/main.py)
   - Parses "migrate" command and options
   - Calls: DBLiftClient(config).migrate()

3. API Client Layer (api/client.py)
   - Loads configuration from file/env/args
   - Creates Provider instance
   - Creates MigrationExecutor
   - Calls: executor.migrate()

4. Migration Engine (core/migration/executor/)
   - MigrateCommand.execute()
   - Loads scripts via ScriptManager
   - Computes state via StateManager
   - Gets connection from Provider
   - Executes SQL statements
   - Records in history table

5. Database Provider Layer (db/plugins/postgresql/)
   - Provider.begin_transaction()
   - QueryExecutor.execute(connection, sql)
   - HistoryManager.record_migration(connection, ...)
   - Provider.commit_transaction()

6. Database Layer
   - Native driver connection executes SQL
   - Returns results
```

---

## API Client Layer

**Location**: `api/client.py`

The `DBLiftClient` class provides the main programmatic API for DBLift operations.

### Core Structure

```python
class DBLiftClient:
    def __init__(self, config: DbliftConfig):
        self.config = config
        self.provider = self._create_provider()
        self.executor = MigrationExecutor(
            config=config,
            provider=self.provider,
            log=self.log
        )

    # Public API Methods
    def migrate(self, **options) -> MigrationResult
    def undo(self, **options) -> MigrationResult
    def baseline(self, **options) -> BaselineResult
    def info(self, **options) -> InfoResult
    def validate(self, **options) -> ValidationResult
    def diff(self, **options) -> DiffResult
    def clean(self, **options) -> CleanResult
    def repair(self, **options) -> RepairResult
    def export_schema(self, **options) -> ExportResult
    def snapshot(self, **options) -> SnapshotResult
```

### Key Responsibilities

1. **Configuration Management**: Load and merge config from multiple sources
2. **Provider Creation**: Instantiate correct database provider
3. **Executor Setup**: Create MigrationExecutor with dependencies
4. **Command Delegation**: Route commands to appropriate handlers
5. **Result Formatting**: Convert internal results to API responses

### Usage Example

```python
from api.client import DBLiftClient
from config import DbliftConfig

# Load configuration
config = DbliftConfig.from_file("dblift.yaml")

# Create client
client = DBLiftClient(config)

# Execute operations
result = client.migrate()
if result.success:
    print(f"Applied {result.migrations_applied} migrations")
else:
    print(f"Error: {result.error_message}")
```

---

## Migration Engine

**Location**: `core/migration/executor/`

The migration engine orchestrates all database change operations.

### Core Components

#### MigrationExecutor

Central orchestrator that manages the migration lifecycle.

**Location**: `core/migration/executor/migration_executor.py`

```python
class MigrationExecutor:
    def __init__(self, config, provider, log):
        self.config = config
        self.provider = provider
        self.log = log

        # Core managers
        self.script_manager = MigrationScriptManager(...)
        self.state_manager = MigrationStateManager(...)
        self.history_manager = provider.history_manager

    def migrate(self, **options) -> MigrationResult:
        """Execute pending migrations"""

    def undo(self, **options) -> MigrationResult:
        """Rollback migrations"""

    def baseline(self, **options) -> BaselineResult:
        """Mark migrations as already applied"""
```

**Key Responsibilities**:
- Load migration scripts
- Compute migration state (pending/applied)
- Execute commands through database provider
- Record results in history table
- Manage schema snapshots

#### Command Pattern

All operations are implemented as Command classes:

**Location**: `core/migration/commands/`

```python
class BaseCommand(ABC):
    def __init__(self, provider, config, log):
        self.provider = provider
        self.config = config
        self.log = log

    @abstractmethod
    def execute(self, **options):
        pass

# Concrete implementations
class MigrateCommand(BaseCommand): ...
class UndoCommand(BaseCommand): ...
class BaselineCommand(BaseCommand): ...
class DiffCommand(BaseCommand): ...
class CleanCommand(BaseCommand): ...
class RepairCommand(BaseCommand): ...
class InfoCommand(BaseCommand): ...
class ValidateCommand(BaseCommand): ...
```

**Benefits**:
- Each operation has isolated logic
- Easy to test independently
- Clear separation of concerns
- Consistent interface

#### State Management

**MigrationStateManager** computes what migrations need to run.

**Location**: `core/migration/state/migration_state_manager.py`

```python
class MigrationStateManager:
    def build_state(
        self,
        scripts_dir: Optional[Path],
        *,
        recursive: bool = True,
        additional_dirs: Optional[Sequence[Path]] = None,
        target_version: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        # ... other filter / strict_mode kwargs
    ) -> MigrationState:
        """
        Loads history via HistoryManager, scans scripts via MigrationScriptManager,
        and produces MigrationState: pending vs applied, undone versions,
        repeatable checksum drift, baseline handling, etc.
        """
```

#### Script Management

**MigrationScriptManager** discovers and loads migration files.

**Location**: `core/migration/scripting/migration_script_manager.py`

```python
class MigrationScriptManager:
    def get_migration_scripts(
        self,
        scripts_dir: Path,
        recursive: bool = True,
        additional_dirs: List[Path] = None,
        dir_recursive_map: Dict[Path, bool] = None,
    ) -> List[Migration]:
        """
        Scans directories for migration files:
        - V<version>__<description>.<ext>  (versioned; .sql, .py, and other registered extensions)
        - R__<description>.<ext>           (repeatable; same extensions as versioned)
        - U<version>__<description>.<ext>  (undo; same extensions as versioned)
        """

    def parse_filename(self, filename: str) -> Tuple[MigrationType, Optional[str], str, List[str]]:
        """Extract type, version, description, and tags from a migration filename."""
```

**Migration File Naming**:
```
V1_0_0__create_users_table.sql
│││││││  │
││││││└──┴─ Description (spaces replaced with _)
│││││└───── Double underscore separator
││││└────── Patch version
│││└─────── Minor version
││└──────── Major version
│└───────── Version indicator
└────────── V = Versioned, R = Repeatable, U = Undo
```

#### Python Migration Executor

**Location**: `core/migration/executors/python_migration_executor.py`

Python migrations (`.py` files) allow complex logic that cannot be expressed in SQL alone.
The `PythonMigrationExecutor` is registered in `ExecutorFactory` alongside the SQL executor.

```python
class PythonMigrationExecutor:
    def execute(self, migration: Migration, ctx: MigrationContext) -> None:
        """Import and call the migrate(ctx) function from the .py script."""
```

`MigrationContext` is injected into the script and provides:
- `ctx.execute(sql, params)` — run a parameterized SQL statement
- `ctx.connection` — direct database connection access
- `ctx.migration` — the `Migration` object with version/description metadata

**Routing**: `ExecutionEngine._execute_via_factory()` checks `migration.format` and dispatches to `PythonMigrationExecutor` for `MigrationFormat.PYTHON`, mirroring the SQL routing.

---

## Database Provider System

**Location**: `db/plugins/`

Each database has a provider that implements a common interface through 5 specialized components.

### Provider Interfaces (ISP)

`BaseProvider` is decomposed into five focused interfaces (`db/provider_interfaces.py`):

| Interface | Methods | Purpose |
|-----------|---------|---------|
| `ConnectionProvider` | `create_connection`, `close_connection`, `is_connected` | Connection lifecycle |
| `QueryProvider` | `execute_query`, `execute_statement` | SQL execution |
| `SchemaProvider` | `schema_exists`, `create_schema`, `get_current_schema` | Schema DDL |
| `TransactionalProvider` | `begin_transaction`, `commit_transaction`, `rollback_transaction`, `supports_transactions` | Transaction control |
| `MigrationProvider` | `get_applied_migrations`, `record_migration`, `get_current_version` | History tracking |

> **Note**: `CosmosDbProvider.supports_transactions()` returns `False` — all transaction guards use `isinstance(provider, TransactionalProvider)` instead of fragile `hasattr` checks.

### Provider Architecture

```
BaseProvider (db/base_provider.py)
├── Interfaces: ConnectionProvider, QueryProvider, SchemaProvider,
│              TransactionalProvider, MigrationProvider
│
├── 5 Component System
│   ├── ConnectionManager  → Creates database connections
│   ├── QueryExecutor      → Executes SQL statements
│   ├── SchemaOperations   → Schema DDL operations
│   ├── LockingManager     → Migration locking
│   └── HistoryManager     → Migration history tracking
│
└── State Management
    ├── self.connection         → Active database connection
    ├── self._in_transaction    → Transaction active flag
    └── self._transaction_depth → Nested transaction counter
```

### Supported Databases

| Database | Provider Location | Connection Type |
|----------|------------------|-----------------|
| PostgreSQL | `db/plugins/postgresql/` | Native SQLAlchemy (`psycopg`) |
| MySQL | `db/plugins/mysql/` | Native SQLAlchemy (`PyMySQL`) |
| SQL Server | `db/plugins/sqlserver/` | Native SQLAlchemy (`pymssql`) |
| Oracle | `db/plugins/oracle/` | Native SQLAlchemy (`python-oracledb`) |
| DB2 | `db/plugins/db2/` | Native SQLAlchemy (`ibm_db_sa`) |
| SQLite | `db/plugins/sqlite/` | Python native (`sqlite3`) |
| Cosmos DB | `db/plugins/cosmosdb/` | Azure SDK (with pseudo-SQL translation) |

### Component Details

#### 1. ConnectionManager

Creates and configures database connections.

```python
class BaseConnectionManager(ABC):
    @abstractmethod
    def create_connection(self) -> Connection:
        """Create new database connection"""

    @abstractmethod
    def configure_connection(self, connection: Connection):
        """Set connection properties (schema, isolation, etc.)"""
```

**PostgreSQL Example**:
```python
class PostgresqlProvider(SqlAlchemyProvider):
    provider_transport = "native"
    canonical_dialect_key = "postgresql"

    def create_connection(self) -> Connection:
        connection = super().create_connection()
        return connection
```

#### 2. QueryExecutor

Executes SQL statements and processes results.

```python
class BaseQueryExecutor(ABC):
    @abstractmethod
    def execute(
        self,
        connection: Connection,
        sql: str,
        params: Optional[List] = None
    ) -> List[Dict]:
        """Execute SQL and return results"""

    @abstractmethod
    def execute_batch(
        self,
        connection: Connection,
        statements: List[str]
    ) -> int:
        """Execute multiple statements"""
```

**Key Design Point**: QueryExecutor receives `connection` as a parameter - it does NOT store it.

#### 3. SchemaOperations

Database schema manipulation.

```python
class BaseSchemaOperations(ABC):
    @abstractmethod
    def create_schema(self, connection: Connection, schema: str):
        """Create database schema"""

    @abstractmethod
    def clean_schema(self, connection: Connection, schema: str):
        """Drop all objects in schema"""

    @abstractmethod
    def schema_exists(self, connection: Connection, schema: str) -> bool:
        """Check if schema exists"""
```

#### 4. LockingManager

Prevents concurrent migrations.

```python
class BaseLockingManager(ABC):
    @abstractmethod
    def acquire_lock(
        self,
        connection: Connection,
        timeout_seconds: int = 60
    ) -> bool:
        """Acquire migration lock"""

    @abstractmethod
    def release_lock(self, connection: Connection):
        """Release migration lock"""
```

**Database-Specific Implementations**:
- **PostgreSQL**: Uses advisory locks (`pg_advisory_lock`)
- **SQL Server**: Uses application locks (`sp_getapplock`)
- **Oracle**: Uses DBMS_LOCK package
- **MySQL**: Uses named locks (`GET_LOCK`)
- **DB2**: Table-based locking
- **SQLite**: Table-based locking with busy timeout
- **Cosmos DB**: ETag-based optimistic concurrency

#### 5. HistoryManager

Tracks applied migrations in database.

```python
class BaseHistoryManager(ABC):
    @property
    @abstractmethod
    def history_table(self) -> str:
        """Name of history table (with naming conventions applied)"""

    @abstractmethod
    def ensure_history_table(self, connection: Connection):
        """Create history table if not exists"""

    @abstractmethod
    def record_migration(
        self,
        connection: Connection,
        schema: str,
        migration_info: Dict[str, Any],
        table_name: Optional[str] = None,
    ) -> None:
        """Record migration execution (migration_info is built by the migration engine)."""

    @abstractmethod
    def get_applied_migrations(
        self,
        connection: Connection
    ) -> List[HistoryRecord]:
        """Retrieve migration history"""
```

**History Table Schema** (PostgreSQL example):
```sql
CREATE TABLE dblift_schema_history (
    installed_rank INTEGER PRIMARY KEY,
    version VARCHAR(50),
    description VARCHAR(200),
    type VARCHAR(20),          -- SQL, REPEATABLE, UNDO_SQL, BASELINE, CALLBACK (Flyway-aligned)
    script VARCHAR(1000),
    checksum INTEGER,
    installed_by VARCHAR(100),
    installed_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    execution_time INTEGER,
    success BOOLEAN
);
```

### Provider Implementation Example

Here's how a provider coordinates its components:

**Location**: `db/plugins/postgresql/provider.py`

```python
class PostgresqlProvider(BaseProvider):
    def __init__(self, config: DbliftConfig, log: Logger):
        super().__init__(config, log)

        # Create components (stateless)
        self.connection_manager = PostgresqlConnectionManager(config, log)
        self.query_executor = PostgresqlQueryExecutor(config, log)
        self.schema_operations = PostgresqlSchemaOperations(config, log)
        self.locking_manager = PostgresqlLockingManager(config, log)
        self.history_manager = PostgresqlHistoryManager(config, log)

        # Connection state (owned by provider)
        self.connection = None
        self._in_transaction = False
        self._transaction_depth = 0

    def create_connection(self) -> Connection:
        """Create new connection and reset transaction state"""
        connection = self.connection_manager.create_connection()
        self.connection = connection

        # IMPORTANT: Reset transaction state for fresh connection
        self._in_transaction = False
        self._transaction_depth = 0

        return connection

    def execute_statement(self, sql: str, schema: Optional[str] = None) -> List[Dict]:
        """Execute SQL statement through QueryExecutor"""
        if not self.connection:
            raise DatabaseError("No active connection")

        # Pass connection explicitly to component
        return self.query_executor.execute(
            self.connection,  # ← Explicit parameter
            sql,
            schema=schema
        )

    def begin_transaction(self):
        """Start transaction"""
        if not self._in_transaction:
            self.connection.commit()  # Clear any pending
            self._in_transaction = True
            self._transaction_depth = 1
        else:
            self._transaction_depth += 1  # Nested

    def commit_transaction(self):
        """Commit transaction"""
        self._transaction_depth -= 1
        if self._transaction_depth == 0:
            self.connection.commit()
            self._in_transaction = False

    def rollback_transaction(self):
        """Rollback transaction"""
        self.connection.rollback()
        self._in_transaction = False
        self._transaction_depth = 0
```

### SQLite Provider (Native Python Example)

SQLite demonstrates how to implement a provider using Python's native database module.

**Location**: `db/plugins/sqlite/provider.py`

```python
class SQLiteProvider(BaseProvider):
    """SQLite provider using Python's native sqlite3 module."""
    
    def __init__(self, config: DbliftConfig, log: Optional[Log] = None):
        super().__init__(config, log)
        
        # Create components (same pattern as other providers)
        self.connection_manager = SQLiteConnectionManager(config, log)
        self.query_executor = SQLiteQueryExecutor(self.connection_manager, log)
        self.locking_manager = SQLiteLockingManager(self.query_executor, log)
        self.schema_operations = SQLiteSchemaOperations(self.query_executor, log)
        self.history_manager = SQLiteHistoryManager(
            self.query_executor, self.schema_operations, config, log
        )
        
        # Connection state
        self.connection: Optional[sqlite3.Connection] = None
    
    def create_connection(self) -> sqlite3.Connection:
        """Create SQLite connection using Python's sqlite3 module."""
        connection = self.connection_manager.create_connection()
        self.connection = connection
        return connection
```

**Key Differences from SQLAlchemy Providers**:

| Aspect | SQLAlchemy Providers | SQLite Provider |
|--------|---------------|-----------------|
| **Connection Module** | SQLAlchemy + Python driver | Python `sqlite3` |
| **Authentication** | Username/password | None (file-based) |
| **Schema Support** | Full schema names | Single "main" schema |
| **Connection URL** | SQLAlchemy URL | File path or `:memory:` |
| **Transaction Control** | Auto-commit off by default | Explicit BEGIN/COMMIT |

**SQLite-Specific Considerations**:
- Uses `isolation_level=None` for autocommit mode with explicit transaction control
- Schema parameter is always "main" (SQLite limitation)
- Locking uses table-based approach with busy timeout
- No stored procedures/functions (these are in application code)
- Limited ALTER TABLE (only ADD COLUMN and RENAME supported)

---

## Configuration System

**Location**: `config/`

Manages application settings from multiple sources.

### Configuration Structure

```python
@dataclass
class DbliftConfig:
    database: DatabaseConfig
    migrations: MigrationsConfig
    history_table: str = "dblift_schema_history"
    snapshot_table: str = "dblift_schema_snapshots"
    max_snapshots: int = 1
    log_level: str = "INFO"
    log_file: Optional[str] = None
    log_format: str = "text"

@dataclass
class DatabaseConfig:
    url: str                    # SQLAlchemy URL or connection string
    username: Optional[str]
    password: Optional[str]
    schema: str
    type: str                   # postgresql, mysql, sqlserver, oracle, db2, sqlite, cosmosdb

@dataclass
class MigrationsConfig:
    directory: Optional[str]           # Single directory
    directories: List[DirectoryConfig] # Multiple directories
    script_encoding: str = "utf-8"
    detect_encoding: bool = False
    recursive: bool = False           # Global recursive default
```

### Configuration Loading

**Precedence** (highest to lowest):
1. CLI arguments (`--db-url`, `--db-schema`, etc.)
2. Environment variables (`DBLIFT_DB_URL`, `DBLIFT_DB_SCHEMA`, etc.)
3. YAML configuration file
4. Default values

**Example**:
```python
from config.config_builder import ConfigBuilder

# Load from file with overrides
config = ConfigBuilder.build(
    file_path="dblift.yaml",
    env_overrides=True,
    database_url="postgresql+psycopg://localhost/testdb",  # CLI override
    database_schema="test_schema"
)
```

### YAML Configuration Example

```yaml
# dblift.yaml
database:
  url: "postgresql+psycopg://localhost:5432/mydb"
  username: "myuser"
  password: "mypass"
  schema: "public"

migrations:
  directories:
    - path: "./migrations/core"
      recursive: true
    - path: "./migrations/features"
      recursive: false
  script_encoding: "utf-8"
  detect_encoding: false

history_table: "dblift_schema_history"
snapshot_table: "dblift_schema_snapshots"
max_snapshots: 3

logging:
  level: "INFO"
  format: "text"
```

---

## SQL Parsing System

### Token-Based Parser (NEW - January 2026)

DBLift now uses a tokenization-based parsing approach inspired by Flyway:

**Architecture:**
- `core/sql_parser/tokens.py` - Token types and Token dataclass
- `core/sql_parser/parser_context.py` - Centralized parser state management
- `core/sql_parser/base_tokenizer.py` - Streaming character-by-character tokenization
- `core/sql_parser/base_statement_parser.py` - Token-based statement splitting

**Dialect-Specific Implementations:**
- `core/sql_parser/oracle/` - Oracle tokenizer and statement parser (Q-quotes, slash delimiters)
- `core/sql_parser/postgresql/` - PostgreSQL tokenizer and parser (dollar quotes, COPY)
- `core/sql_parser/mysql/` - MySQL tokenizer and parser (DELIMITER, backticks)
- `core/sql_parser/sqlserver/` - SQL Server tokenizer and parser (GO, brackets)

**Key Features:**
- ✅ Single-pass streaming tokenization
- ✅ Explicit block depth tracking
- ✅ Dialect-specific string literal handling
- ✅ Fallback to regex for edge cases
- ✅ 98.2% test pass rate (504/513 tests)

See: `docs/architecture/tokenization_parser_architecture.md` for details.

### Original SQL Parsing System

**Location**: `core/sql_parser/`

Parses SQL scripts to extract statements and handle dialect-specific syntax.

#### 3.1 Provider Architecture

Each database has a modular provider with five specialized components:

**1. Connection Manager**
- Native connection management
- SQLAlchemy engine/connection lifecycle
- Connection pooling
- Transaction control

**2. Query Executor**
- SQL statement execution
- Result set processing
- Database-specific type conversion
- Parameter binding

**3. Locking Manager**
- Migration lock acquisition/release
- Uses database-native locking when available
- Fallback to table-based locking
- Timeout handling

**4. Schema Operations**
- Schema creation/deletion
- Object enumeration
- Metadata queries
- Database version detection

**5. History Manager**
- Migration history table management
- History record insertion/querying
- Database-specific optimizations
- Checksum management

#### 3.2 Provider Structure

```
db/providers/
├── oracle/
│   ├── connection_manager.py
│   ├── query_executor.py
│   ├── locking_manager.py      # Uses DBMS_LOCK package
│   ├── schema_operations.py
│   └── history_manager.py
├── sqlserver/
│   ├── connection_manager.py
│   ├── query_executor.py
│   ├── locking_manager.py      # Uses sp_getapplock
│   ├── schema_operations.py
│   └── history_manager.py
├── postgresql/
│   ├── connection_manager.py
│   ├── query_executor.py
│   ├── locking_manager.py      # Uses advisory locks
│   ├── schema_operations.py
│   └── history_manager.py
├── db2/
│   └── ... (similar structure)
├── mysql/
│   └── ... (similar structure)
└── cosmosdb/
    ├── connection_manager.py    # Uses Azure SDK
    ├── query_executor.py        # CosmosDB SQL API
    ├── locking_manager.py       # ETag-based optimistic concurrency
    ├── schema_operations.py     # Container management
    └── history_manager.py       # Document-based history
```

#### 3.3 Native Driver Integration

**NativeConnectionManager** (`db/native_connection_manager.py`)
- Owns the SQLAlchemy `Engine`
- Opens and closes SQLAlchemy `Connection` objects
- Disposes the engine on provider close

**Plugin URL builders** (`db/plugins/<dialect>/sqlalchemy_url.py`)
- Build SQLAlchemy URLs from the plugin config object
- Keep dialect-specific URL rules inside the plugin

**Connection Flow (SQLAlchemy Providers):**
```
1. ProviderRegistry resolves the plugin
2. Plugin-owned SQLAlchemy URL builder creates the URL
3. NativeConnectionManager creates the Engine
4. Provider opens a Connection
5. Ready for SQL execution
```

**Connection Flow (SDK Providers - CosmosDB):**
```
1. Azure SDK initialized (azure-cosmos, azure-identity)
2. CosmosClient created with endpoint/key or managed identity
3. Database proxy obtained
4. Container clients created on-demand
5. Ready for CosmosDB SQL API execution
```

**Note**: CosmosDB uses the Azure SDK for Python instead of SQLAlchemy.

#### 3.4 CosmosDB Architecture (SDK Provider)

**Location**: `/db/providers/cosmosdb/`

CosmosDB uses the Azure SDK for Python instead of SQLAlchemy connections.

**Key Differences from SQLAlchemy Providers:**

1. **Connection Management**
   - Uses `azure.cosmos.CosmosClient` instead of a SQLAlchemy `Connection`
   - Supports account key authentication or Azure Managed Identity
   - Handles CosmosDB Emulator with SSL verification bypass
   - Connection represented as `DatabaseProxy` object

2. **Query Execution**
   - Executes CosmosDB SQL API queries (T-SQL-like syntax)
   - Supports `CREATE CONTAINER`, `SELECT`, `INSERT`, `UPDATE`, `DELETE`
   - Handles JSON data types (OBJECT, ARRAY, BOOLEAN) correctly
   - Parameter substitution using `@paramN` placeholders
   - Container-based operations instead of table-based

3. **Locking Mechanism**
   - Primary: Native ETag-based optimistic concurrency control
   - Fallback: Document-based locking using `dblift_migration_lock` container
   - Lock document includes expiration timestamp
   - Automatic cleanup of expired locks

4. **Schema Operations**
   - Containers instead of tables (mapped to SQL model as tables)
   - Partition key configuration (`/id`, `/version`, etc.)
   - Throughput provisioning (RU/s) support
   - Indexing policy and unique key policy configuration
   - Time-to-live (TTL) support

5. **History Management**
   - Document-based history in `dblift_schema_history` container
   - Partition key: `/version` (not `/id`)
   - Uses `upsert_item` for idempotent history recording
   - JSON document structure instead of relational rows

6. **Schema Introspection**
   - Infers schema from actual documents (schema-less database)
   - Samples documents to determine column types
   - Handles nested JSON objects and arrays
   - Type inference: STRING, NUMBER, BOOLEAN, OBJECT, ARRAY

7. **SQL Parsing**
   - Uses `SqlServerRegexParser` (T-SQL-like syntax)
   - Recognizes `CREATE CONTAINER` statements
   - Extracts partition key, indexing policy, unique keys
   - Normalizes identifiers to lowercase (case-insensitive)

**Dependencies:**
- `azure-cosmos>=4.5.0` - Azure Cosmos DB SDK
- `azure-identity>=1.15.0` - Azure authentication (for managed identity)

**Configuration Example:**
```yaml
database:
  type: "cosmosdb"
  account_endpoint: "https://account.documents.azure.com:443/"
  account_key: "your-key"
  database_name: "your-database"
```

---

### 4. Logging System

**Location**: `/core/logger`

Flexible logging with multiple outputs and formats.

**Key Components:**
- `LogFactory` - Creates and configures loggers
- `DbliftLogger` - Enhanced logger with filtering
- `NullLog` - No-op logger (default when no logger is injected; eliminates `if self.log:` guards everywhere)
- `OutputFormatter` - Base class for formatters
- `MigrationJournal` - Detailed execution tracking

**NullLog Pattern:**

All classes that accept a `log` parameter now default to `NullLog()` instead of `None`:

```python
class MyComponent:
    def __init__(self, log: Log = NullLog()):
        self.log = log  # Always safe to call — NullLog is a no-op
```

This means callers never need to pass a logger; components always have a safe logger to call.

**Output Formats:**
- **TEXT**: Human-readable plain text
- **JSON**: Machine-readable structured data
- **HTML**: Rich formatted reports with charts

**Log Levels:**
- DEBUG: Detailed diagnostic information
- INFO: General informational messages
- WARNING: Warning messages
- ERROR: Error messages
- CRITICAL: Critical errors

**Migration Journal:**
- Tracks each SQL statement execution
- Records timing and performance metrics
- Identifies slow-running statements
- **Always in-memory only** - never persists to disk
- Thread-safe operations
- No CLI options or config file settings to control persistence

---

## Refactored Component Architecture (2024)

### Factory-Based Component Creation

DBLift now uses a comprehensive factory pattern system for creating dialect-specific components:

#### 1. AlterGenerator Architecture

**Location**: `/core/migration/sql_generation/alter/`

**Components:**
- `BaseAlterGenerator` - Abstract base class defining the interface
- `AlterGeneratorFactory` - Creates dialect-specific generators
- Dialect-specific implementations: `PostgreSQLAlterGenerator`, `OracleAlterGenerator`, `MySQLAlterGenerator`, `SqlServerAlterGenerator`, `DB2AlterGenerator`

**Key Features:**
- Proper case preservation for Oracle and DB2 identifiers
- Dialect-specific SQL syntax handling
- Consistent interface across all database types

#### 2. SQL Generation Architecture

**Location**: `/core/migration/sql_generation/`

**Enhanced Components:**
- `BaseSqlGenerator` - Abstract base class with generic dispatch mechanism
- `SqlGeneratorFactory` - Creates dialect-specific SQL generators
- Statement Generator Pattern: Moved `create_statement` logic from SQL model classes to generators

**Refactored SQL Models:**
All 17 SQL model classes now delegate SQL generation to appropriate generators:
- `Table`, `View`, `Index`, `Procedure`, `Sequence`, `UserDefinedType`, `Trigger`
- `Package`, `ForeignServer`, `ForeignDataWrapper`, `Extension`, `Event`
- `DatabaseLink`, `Partition`, `Module`, `LinkedServer`, `Synonym`

#### 3. Export Handler Architecture

**Location**: `/cli/export/`

**Components:**
- `BaseExportHandler` - Abstract base class for export operations
- `ExportHandlerFactory` - Creates database-specific export handlers
- Dialect-specific implementations for all supported databases

**Benefits:**
- Reduced monolithic `export_schema_command.py` from 1,729 lines
- Separated dialect-specific export logic
- Improved maintainability and testability

#### 4. Database Provider Enhancements

**Enhanced Components:**
- `BaseSchemaOperations` - Standardized schema operations interface
- `BaseQueryExecutor` - Consistent query execution interface
- `BaseHistoryManager` - Unified history management with common utilities

**Factory Integration:**
- `SchemaOperationsFactory` - Creates provider-specific schema operations
- `QueryExecutorFactory` - Creates provider-specific query executors
- `HistoryManagerFactory` - Creates provider-specific history managers

### Code Quality Achievements

**Testing Success:**
- Reduced unit test failures from 32 to 0 (100% success rate)
- Enhanced integration test coverage
- Comprehensive factory pattern testing

**Code Standards:**
- Full Black formatting compliance
- Complete isort import sorting
- 100% MyPy type checking compliance
- Enhanced error handling and logging

**Architecture Benefits:**
- Improved code maintainability and readability
- Enhanced extensibility for new database support
- Better separation of concerns
- Consistent interfaces across all components

---

## Database Provider Architecture

### Modular Design Philosophy

Each database provider follows the **5-Component Pattern**:

1. **Connection Manager**: Database connectivity
2. **Query Executor**: SQL execution and result processing
3. **Locking Manager**: Concurrent migration protection
4. **Schema Operations**: Schema management
5. **History Manager**: Migration tracking

**Benefits:**
- **Separation of concerns**: Each component has focused responsibilities
- **Database-specific optimizations**: Use native features (Oracle DBMS_LOCK, PostgreSQL advisory locks)
- **Consistent patterns**: All providers follow identical structure
- **Easier testing**: Small, focused modules are easier to test
- **Maintainability**: Changes isolated to specific components

### Error Handling

**Centralized Error Handler** (`db/error_handler.py`)

All database providers use a centralized error handling system:

**Features:**
- Automatic error categorization (network, timeout, locking, resource)
- Vendor-specific error code mapping
- Automatic retry with exponential backoff
- Detailed error reporting

**Error Categories:**
- **NETWORK**: Connection failures, network timeouts
- **TIMEOUT**: Query timeouts, lock timeouts
- **LOCKING**: Deadlocks, lock conflicts
- **RESOURCE**: Out of memory, connection limits
- **SCHEMA**: Object not found, duplicate object
- **PERMISSION**: Access denied errors
- **DATA**: Data type errors, constraint violations
- **SYNTAX**: SQL syntax errors

**Retry Strategy:**
```python
@with_error_handling()
def execute_statement(self, sql: str, params=None):
    # Automatic retry for transient errors
    # Exponential backoff: 1s, 2s, 4s
    # Jitter to avoid thundering herd
    pass
```

**Configuration:**
```yaml
error_handling_enabled: true
max_retries: 3
retry_delay: 1.0
retry_backoff: 2.0
retry_jitter: 0.2
retryable_error_categories:
  - network
  - timeout
  - locking
  - resource
```

---

## SQL Parsing & Analysis

**Location**: `/core/migration/parsers`

DBLift uses a **hybrid parsing strategy** combining regex and AST-based parsing.

### Hybrid Parser Architecture

**Why Hybrid?**

- **Regex**: Excellent for statement splitting and procedural languages
- **SqlGlot (AST)**: Superior for pure SQL analysis and dependencies

**Strategy:**
1. **Regex splitting** for all SQL (handles PL/SQL, T-SQL, PL/pgSQL blocks)
2. **SqlGlot enhancement** for pure SQL (dependency extraction, complexity analysis)
3. **Smart detection** automatically chooses the right approach

### Supported Dialects

| Dialect | Parser | Accuracy | Notes |
|---------|--------|----------|-------|
| PostgreSQL | Hybrid (Regex + SqlGlot) | ~95% | Full PL/pgSQL support |
| Oracle | Hybrid (Regex + SqlGlot) | ~95% | PL/SQL blocks handled |
| SQL Server | Hybrid (Regex + SqlGlot) | ~95% | T-SQL procedures supported |
| MySQL | Hybrid (Regex + SqlGlot) | ~95% | DELIMITER handling |
| DB2 | Regex only | ~85% | SqlGlot doesn't support DB2 |
| CosmosDB | Regex only | ~90% | T-SQL-like syntax, uses SqlServerRegexParser |

### SQL Object Model

Parsed SQL is represented as structured objects:

**Core Objects:**
- `Table` - Tables with columns and constraints
- `View` - Views with definitions
- `Index` - Indexes with columns and type
- `Sequence` - Sequences with increment/min/max
- `Procedure` - Stored procedures
- `Function` - User-defined functions
- `Trigger` - Database triggers
- `Synonym` - Object aliases (Oracle, SQL Server, DB2)
- `UserDefinedType` - ENUM, COMPOSITE, DOMAIN types
- `Extension` - PostgreSQL extensions
- `Package` - Oracle packages
- `Event` - MySQL scheduled events
- `Partition` - Table partitions

**Benefits:**
- Type-safe representation
- Dialect-agnostic
- Easy to query and manipulate
- Foundation for validation and drift detection

---

## Advanced Subsystems

### 1. Schema Introspection

**Location**: `/db/introspection`

Comprehensive schema introspection using SQLAlchemy Inspector + vendor queries.

#### Architecture

**Two-Layer Strategy:**

1. **SQLAlchemy Inspector Layer (70-80% coverage)**
   - Uses SQLAlchemy's inspection API
   - Database-agnostic
   - Tables, columns, PK, FK, unique constraints, basic indexes

2. **Vendor Query Layer (+15-20% coverage)**
   - Database-specific catalog queries
   - Inspired by SQLAlchemy
   - Check constraints, sequences, views with definitions, triggers, UDTs

**Combined Coverage: 95%+ of enterprise schema needs**

#### Vendor-Specific Queries

| Feature | PostgreSQL | Oracle | SQL Server | MySQL | DB2 | CosmosDB |
|---------|-----------|--------|------------|-------|-----|----------|
| Check Constraints | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Sequences | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ |
| Views + Definitions | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Triggers | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Synonyms | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ |
| User-Defined Types | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Extensions | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Containers (Tables) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Indexes | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Partition Keys | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Throughput (RU/s) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

#### Usage Example

```python
class BaseSqlParser(ABC):
    @abstractmethod
    def parse_script(self, sql: str) -> List[str]:
        """Split SQL script into individual statements"""

    @abstractmethod
    def extract_objects(self, sql: str) -> List[SqlObject]:
        """Extract DDL objects from SQL"""
```

### Dialect-Specific Parsers

| Database | Parser | Delimiter Handling |
|----------|--------|-------------------|
| PostgreSQL | `PostgresqlRegexParser` | `;` and `$$` |
| MySQL | `MySqlRegexParser` | `;` and custom `DELIMITER` |
| SQL Server | `SqlServerRegexParser` | `;` and `GO` |
| Oracle | `OracleRegexParser` | `;` and `/` |
| DB2 | `Db2RegexParser` | `;` and `@` |
| SQLite | `SQLiteRegexParser` | `;` and `BEGIN/END` blocks |
| Cosmos DB | `SqlServerRegexParser` | T-SQL-like syntax |

### Statement Splitting

Parsers handle complex scenarios:

1. **String Literals**: Don't split on `;` inside `'strings'`
2. **Comments**: Ignore delimiters in `-- comments` and `/* blocks */`
3. **Dollar Quoting**: PostgreSQL `$$function body$$`
4. **Custom Delimiters**: MySQL `DELIMITER //`
5. **Batch Separators**: SQL Server `GO`

**Example**:
```sql
-- PostgreSQL script
CREATE FUNCTION get_user(id INT) RETURNS TEXT AS $$
BEGIN
    -- This semicolon is inside function;
    RETURN 'user';
END;
$$ LANGUAGE plpgsql;  -- Parser knows this is ONE statement

CREATE TABLE users (id INT);  -- This is a SECOND statement
```

---

## Schema Management

### Schema Introspection

**Location**: `db/introspection/`

Reads current database schema for diff and export operations. The introspection system has been refactored into a modular, extractor-based architecture for improved maintainability and organization.

#### Architecture Overview

The schema introspection system follows a **hybrid orchestrator + extractor pattern**:

```
SchemaIntrospector (Orchestrator)
    ├── BaseIntrospector (Base class)
    │   ├── Connection management
    │   ├── Result tracking
    │   └── Common initialization
    │
    └── Object-Specific Extractors (delegation)
        ├── TableExtractor
        ├── ColumnExtractor
        ├── ConstraintExtractor
        ├── IndexExtractor
        ├── ViewExtractor
        ├── SequenceExtractor
        ├── TriggerExtractor
        ├── ProcedureExtractor
        └── MiscExtractor (events, packages, synonyms, UDTs, extensions, etc.)
```

#### Directory Structure

```
db/introspection/
├── schema_introspector.py          # Main orchestrator (2,064 lines, down from 4,543)
├── base_introspector.py            # Base class with common functionality
├── introspector_factory.py         # Factory for creating dialect-specific introspectors
├── vendor_queries_factory.py       # Factory for vendor-specific queries
│
├── core/                           # Common utilities
│   ├── sqlalchemy_metadata.py     # SQLAlchemy Inspector metadata management
│   └── utils.py                   # Shared utility functions
│
├── extractors/                     # Object-specific extractors
│   ├── base_extractor.py          # Base class for all extractors
│   ├── table_extractor.py         # Tables
│   ├── column_extractor.py        # Columns
│   ├── constraint_extractor.py    # Constraints (PK, FK, UNIQUE, CHECK)
│   ├── index_extractor.py         # Indexes
│   ├── view_extractor.py          # Views and materialized views
│   ├── sequence_extractor.py      # Sequences
│   ├── trigger_extractor.py       # Triggers
│   ├── procedure_extractor.py     # Procedures and functions
│   └── misc_extractor.py          # Events, packages, synonyms, UDTs, extensions, etc.
│
└── databases/                      # Database-specific implementations
    ├── postgresql/
    │   ├── postgresql_introspector.py
    │   └── postgresql_queries.py
    ├── mysql/
    ├── oracle/
    ├── sqlserver/
    ├── db2/
    ├── sqlite/
    └── cosmosdb/
```

#### SchemaIntrospector (Orchestrator)

**Location**: `db/introspection/schema_introspector.py`

Acts as an orchestrator that delegates to specialized extractors:

```python
class SchemaIntrospector(BaseIntrospector):
    """
    Orchestrates schema introspection by delegating to specialized extractors.
    
    This class coordinates object extraction without containing the actual
    extraction logic, which is handled by dedicated extractor classes.
    """
    
    def __init__(self, provider, log=None, use_vendor_queries=True):
        super().__init__(provider, log, use_vendor_queries)
        
        # Lazy initialization - extractors created when needed
        self._table_extractor: Optional[TableExtractor] = None
        self._column_extractor: Optional[ColumnExtractor] = None
        # ... other extractors
    
    def _get_table_extractor(self) -> TableExtractor:
        """Get or create table extractor (lazy initialization)"""
        if self._table_extractor is None:
            self._ensure_metadata()
            self._table_extractor = TableExtractor(
                provider=self.provider,
                connection=self.connection,
                metadata=self.metadata,
                vendor_queries=self.vendor_queries,
                dialect=self.dialect,
                log=self.log,
                result_tracker=self if self._track_results else None,
                column_extractor=self._get_column_extractor(),
                constraint_extractor=self._get_constraint_extractor(),
            )
        return self._table_extractor
    
    def get_tables(self, schema: str, include_views: bool = False, 
                   table_pattern: str = "%") -> List[Table]:
        """Delegate to table extractor"""
        return self._get_table_extractor().get_tables(
            schema, include_views, table_pattern
        )
```

**Key Features**:
- **Lazy Initialization**: Extractors are created only when needed, reducing startup overhead
- **Delegation Pattern**: Methods delegate to appropriate extractors
- **Reduced Size**: File size reduced from 4,543 lines to 2,064 lines (54.5% reduction)
- **Better Organization**: Logic separated by object type into focused modules

#### Object Extractors

**Location**: `db/introspection/extractors/`

Each extractor handles a specific object type:

```python
class BaseExtractor(ABC):
    """
    Base class for all object extractors.
    
    Provides common functionality:
    - SQLAlchemy Inspector metadata access
    - Row value extraction utilities
    - Result tracking integration
    - Database-specific override hooks
    """
    
    def __init__(self, provider, connection=None, metadata=None,
                 vendor_queries=None, dialect: str = "unknown",
                 log=None, result_tracker=None):
        self.provider = provider
        self.connection = connection
        self.metadata = metadata
        self.vendor_queries = vendor_queries
        self.dialect = dialect
        self.log = log
        self.result_tracker = result_tracker
        self.metadata_extractor = SqlAlchemyMetadataExtractor(provider.engine)
```

**Extractor Classes**:

| Extractor | Purpose | Key Methods |
|-----------|---------|-------------|
| `TableExtractor` | Tables with columns and constraints | `get_tables()` |
| `ColumnExtractor` | Column metadata | `get_columns()` |
| `ConstraintExtractor` | Primary keys, foreign keys, unique, check | `_get_constraints()`, `_get_primary_key()`, `_get_foreign_keys()`, `get_check_constraints()` |
| `IndexExtractor` | Index definitions | `get_indexes()` |
| `ViewExtractor` | Views and materialized views | `get_views()`, `get_materialized_views()` |
| `SequenceExtractor` | Sequence definitions | `get_sequences()` |
| `TriggerExtractor` | Trigger definitions | `get_triggers()` |
| `ProcedureExtractor` | Procedures and functions | `get_procedures()`, `get_functions()` |
| `MiscExtractor` | Events, packages, synonyms, UDTs, extensions, etc. | Various get methods |

**Extractor Dependencies**:

Some extractors depend on others:
- `TableExtractor` depends on `ColumnExtractor` and `ConstraintExtractor`
- Extractors share the same connection and metadata for consistency

#### Database-Specific Introspectors

**Location**: `db/introspection/databases/<dialect>/`

Database-specific introspectors extend `BaseIntrospector` and override specific methods:

```python
class PostgreSQLIntrospector(BaseIntrospector):
    """PostgreSQL-specific introspection overrides."""
    
    def get_tables(self, schema: str, **kwargs) -> List[Table]:
        # PostgreSQL-specific table extraction logic
        # Can override default behavior from SchemaIntrospector
        pass
```

**Structure**:
- Each database has its own subdirectory (`postgresql/`, `mysql/`, `oracle/`, etc.)
- Contains both introspector and vendor query implementations
- Uses lazy imports to avoid circular dependencies

#### Common Utilities

**Location**: `db/introspection/core/`

Shared utilities extracted from the monolithic file:

**`core/utils.py`**:
- `get_row_value()`: Extract values from query result rows
- `parse_pg_options()`: Parse PostgreSQL option arrays
- `parse_json_array()`: Parse JSON arrays from vendor queries
- `strip_leading_comments()`: Remove comments from SQL text
- `to_int()`, `to_bool()`: Type conversion utilities

**`core/sqlalchemy_metadata.py`**:
- `SqlAlchemyMetadataExtractor`: Encapsulates SQLAlchemy Inspector metadata access
- Provides lazy initialization of inspector metadata
- Uses the provider-owned SQLAlchemy engine

#### Benefits of Refactoring

1. **Reduced Complexity**: Main file reduced from 4,543 lines to 2,064 lines (54.5% reduction)
2. **Better Organization**: Logic separated by object type
3. **Easier Maintenance**: Changes to one object type don't affect others
4. **Improved Testability**: Extractors can be tested independently
5. **Clearer Responsibilities**: Each extractor has a single, focused purpose
6. **Database Organization**: Database-specific code organized in subdirectories
7. **Reusable Utilities**: Common functions extracted to shared modules

#### Usage Example

```python
from db.introspection.schema_introspector import SchemaIntrospector

# Create introspector
introspector = SchemaIntrospector(provider, log=log)

# Introspect schema - extractors created automatically when needed
tables = introspector.get_tables("public")
views = introspector.get_views("public")
indexes = introspector.get_indexes("public", "users")
sequences = introspector.get_sequences("public")

# Or use database-specific introspector
from db.introspection.databases.postgresql import PostgreSQLIntrospector
pg_introspector = PostgreSQLIntrospector(provider, log=log)
```

#### Adding New Object Types

To add introspection for a new object type:

1. Create new extractor in `db/introspection/extractors/`
2. Add lazy initialization method to `SchemaIntrospector`
3. Add delegation method to `SchemaIntrospector`
4. Update `BaseIntrospector` if needed for common functionality

### Schema Snapshots

**Location**: `core/migration/snapshots/`

Captures point-in-time schema state for drift detection.

```python
class SchemaSnapshotService:
    def capture_snapshot(
        self,
        connection: Connection,
        version: str
    ) -> SchemaSnapshot:
        """Capture current schema state"""

    def store_snapshot(
        self,
        connection: Connection,
        snapshot: SchemaSnapshot
    ):
        """Save snapshot to database"""

    def load_snapshot(
        self,
        connection: Connection,
        version: Optional[str] = None
    ) -> SchemaSnapshot:
        """Load snapshot from database (latest if version=None)"""
```

**Storage**: Snapshots are JSON documents stored in `dblift_schema_snapshots` table.

**Use Cases**:
- **Diff Command**: Compare migrations vs actual database
- **Export Schema**: Generate SQL from snapshot instead of live introspection
- **Drift Detection**: Track unmanaged changes

### Schema Validation & Quality Assurance

**Location**: `core/validation/`, `db/introspection/`

Comprehensive validation framework for ensuring introspection quality and schema consistency.

#### IntrospectionResult Tracking

**Location**: `db/introspection/result.py`

Tracks introspection quality and completeness:

```python
class IntrospectionResult:
    success: bool
    warnings: List[IntrospectionIssue]
    errors: List[IntrospectionIssue]
    missing_objects: List[Dict[str, Any]]
    completeness_score: float  # 0-100%
    confidence: ConfidenceLevel  # HIGH, MEDIUM, LOW, VERY_LOW
```

**Features**:
- Property-level capture tracking (`ObjectCaptureStatus`)
- Completeness scoring (0-100%)
- Confidence levels based on capture quality
- Missing object detection

#### Validation Framework

**Location**: `core/validation/`

Four validators work together to ensure schema quality:

1. **CompletenessValidator** (`completeness_validator.py`)
   - Verifies all expected objects are present
   - Checks required properties are captured
   - Validates object counts match expectations

2. **ConsistencyValidator** (`consistency_validator.py`)
   - Validates foreign key references exist
   - Verifies index references valid columns
   - Checks constraint relationships
   - Validates view dependencies

3. **AccuracyValidator** (`accuracy_validator.py`)
   - Compares captured state vs live database
   - Detects drift between captures
   - Verifies round-trip accuracy

4. **StateValidator** (`state_validator.py`)
   - Coordinates all validation checks
   - Provides unified validation interface
   - Generates overall status with confidence scoring

**Usage**:
```python
from core.validation.state_validator import StateValidator

validator = StateValidator()
result = validator.validate_schema_state(
    tables=tables,
    views=views,
    indexes=indexes,
    expected_counts={"tables": 10, "views": 5}
)

if not result.passed:
    for issue in result.issues:
        print(f"{issue.severity}: {issue.message}")
```

#### Schema Comparison

Schema comparison is handled by `core/comparison/comparator.py`:

# Export managed objects only (objects defined in applied migrations)
dblift export-schema --managed-only --output migrations/managed.sql

# Export unmanaged objects only (brownfield baseline)
dblift export-schema --unmanaged-only --output migrations/unmanaged.sql

# Export with migration filtering (tags, versions)
dblift export-schema --managed-only --tags feature1 --output migrations/feature.sql
dblift export-schema --managed-only --target-version=1.5.0 --output migrations/up_to_1_5.sql
dblift export-schema --managed-only --versions 1.0.0,1.1.0 --output migrations/specific.sql

# Split by type
dblift export-schema --split-by-type --output-dir migrations/baseline/

# Multiple scripts directories with recursion
dblift export-schema --scripts migrations --scripts shared/migrations --managed-only --output migrations/managed.sql
```

**Key Features:**
- Supports multiple scripts directories (via `--scripts` flag, can be specified multiple times)
- Recursive migration file search with per-directory control
- Schema filtering: Only exports objects from the target schema (specified via `--schema` or config)
- Migration filtering: Filter which migrations are considered via `--tags`, `--exclude-tags`, `--versions`, `--exclude-versions`, `--target-version`
- Uses `MigrationScriptManager` and `MigrationStateManager` for consistent migration handling
- Properly detects all object types (tables, views, functions, triggers, procedures, indexes, sequences)

---

## Integration & Deployment

### CLI System

**Location**: `/cli`

Production CLI with comprehensive command set.

#### Command Structure

```
dblift [global-options] command [command-options]
```

**Core Commands:**

| Command | Purpose |
|---------|---------|
| `migrate` | Apply pending migrations |
| `undo` | Roll back migrations |
| `info` | Show migration status |
| `validate` | Check migration scripts |
| `baseline` | Mark version as applied |
| `clean` | Remove schema objects |
| `repair` | Fix history table |
| `diff` | Detect schema drift |
| `export-schema` | Export database schema |
| `snapshot` | Export schema snapshot to JSON model |
| `validate-sql` | Validate SQL without DB |
| `import-flyway` | Import Flyway history from `flyway_schema_history` by default; `--flyway-table` overrides the source table, while `--table` selects the target DBLift history table |
| `db` | Database utilities |

#### Output Conventions

- CLI commands follow a standardized layout: headers, tables, and completion banners share the same spacing and separators across the tool.
- `migrate`, `info`, and `undo` announce the current schema version before processing so operators immediately know the starting point.
- The migration status table now includes an **Undoable** column, reflecting whether a matching undo script exists for each version.
- `export-schema` and `snapshot` commands display consistent headers with database name, schema name, masked database URL, and filtering options.
- `export-schema` prints object counts before writing files, then finishes with a summary that includes execution time.
- Every command ends with a `Command <name> completed successfully in <duration>` banner, making automation logs easy to scan.
#### Command Chaining

DBLift supports running multiple commands in sequence:

```bash
# Validate, then migrate
dblift validate migrate

# Check status, migrate, check again
dblift info migrate info

# Complex workflow
dblift validate info migrate diff
```

---

### Docker Architecture

**Location**: `/` (Dockerfiles)

Two Docker images for different use cases:

#### Full Image (`Dockerfile`)

Complete installation with DBLift runtime dependencies.

**Includes:**
- Python 3.11
- All DBLift dependencies
- Native Python database drivers must be installed separately through extras

**Use Cases:**
- Running migrations
- Database connectivity required
- Full feature set

**Usage:**
```bash
docker run --rm \
  -v $(pwd)/migrations:/workspace/migrations \
  -v $(pwd)/dblift.yaml:/workspace/dblift.yaml \
  -e DBLIFT_DB_URL="postgresql+psycopg://..." \
  ghcr.io/cmodiano/dblift:latest \
  migrate
```

#### Validation Image (`Dockerfile.validation`)

Lightweight image for SQL validation only (~150MB).

**Includes:**
- Python 3.11 (slim)
- Validation dependencies only
- No live database driver dependencies

**Use Cases:**
- CI/CD validation
- Pre-commit hooks
- Code review

**Usage:**
```bash
docker run --rm \
  -v $(pwd)/migrations:/workspace/migrations \
  -v $(pwd)/.dblift_rules.yaml:/workspace/.dblift_rules.yaml \
  ghcr.io/cmodiano/dblift:validation-latest \
  migrations/ \
  --dialect postgresql \
  --rules-file .dblift_rules.yaml
```

---

### Build & Distribution

**Location**: `/scripts/build_distributions.py`

Creates platform-specific distributions with DBLift and its Python runtime dependencies.

#### Build Process

1. **Platform Detection**
   - Detects OS (Windows, macOS, Linux)
   - Detects architecture (x86_64, ARM64)

2. **Dependency Packaging**
   - Includes DBLift's Python dependencies
   - Native database drivers are installed through pip extras

3. **Package Structure**
   ```
   dblift-{platform}-{arch}/
   ├── dblift/           # Python package
   └── dblift            # Launcher script
   ```

4. **Distribution Creation**
   - Windows: ZIP archive
   - Unix/macOS: TAR.GZ archive
   - Permissions preserved
   - Code signing support (macOS)

---

## Design Patterns & Decisions

### Design Patterns Used

**Factory Pattern**
- `ProviderRegistry` - Registers and creates database providers (replaces the removed `ProviderFactory`)
- `LogFactory` - Creates loggers
- `OutputFormatterFactory` - Creates formatters
- `VendorQueriesFactory` - Creates vendor-specific queries
- `AlterGeneratorFactory` - Creates dialect-specific ALTER statement generators
- `SqlGeneratorFactory` - Creates dialect-specific SQL generators
- `ExportHandlerFactory` - Creates database-specific export handlers
- `SchemaOperationsFactory` - Creates database-specific schema operations
- `QueryExecutorFactory` - Creates database-specific query executors
- `HistoryManagerFactory` - Creates database-specific history managers
- `IntrospectorFactory` - Creates database-specific schema introspectors

**Strategy Pattern**
- Database providers (Oracle, PostgreSQL, SQL Server, etc.)
- Log implementations (console, file, multiple formats)
- Output formatters (TEXT, JSON, HTML, SARIF)

**Command Pattern**
- Migration operations (migrate, undo, validate, etc.)
- Each command encapsulates operation logic

**Template Method**
- `SqlAlchemyProvider` base class with customization points
- `OutputFormatter` base class for different formats

**Adapter Pattern**
- Plugin-owned SQLAlchemy URL builders adapt config objects to driver URLs

**Decorator Pattern**
- `@with_error_handling()` for automatic retry logic

---

### Error Handling Strategy

#### Centralized Error Management

All database errors flow through `db/error_handler.py`:

**Error Categorization:**
```python
# Schema comparison is handled by core/comparison/comparator.py
# See Comparator.compare_schemas() for implementation
        actual_objects: Dict[str, List[SqlObject]],
        schema: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Detect missing tables, columns, constraints, indexes, views"""
```

### Schema Normalization

**Location**: `core/normalization/`

Components for standardizing schema representation across databases.

#### Canonical Ordering

**Location**: `core/normalization/object_orderer.py`

Provides deterministic ordering of SQL objects:

```python
class ObjectOrderer:
    @classmethod
    def sort_objects(cls, objects: List[SqlObject]) -> List[SqlObject]:
        """
        Orders by:
        1. Object type (tables, views, indexes, etc.)
        2. Dependency depth
        3. Schema (alphabetically)
        4. Name (alphabetically, case-insensitive)
        """
```

**Vendor-Specific Handling:**
- SQL Server error codes (e.g., 1205 = deadlock)
- Oracle error codes (e.g., ORA-00060 = deadlock)
- PostgreSQL error codes (e.g., 40P01 = deadlock)
- DB2 SQLCODEs (e.g., -911 = deadlock)
- CosmosDB HTTP status codes (e.g., 429 = rate limit, 500 = service error)

#### Type Normalization

**Location**: `core/normalization/type_mapper.py`

Maps database-specific types to canonical forms:

```python
class CanonicalTypeMapper:
    def to_canonical(
        self,
        dialect: str,
        db_type: str,
        version: Optional[DatabaseVersion] = None
    ) -> str:
        """Convert database-specific type to canonical form"""
    
    def from_canonical(
        self,
        dialect: str,
        canonical_type: str,
        version: Optional[DatabaseVersion] = None
    ) -> str:
        """Convert canonical type to database-specific form"""
```

**Features**:
- Cross-dialect type equivalence
- Version-specific mappings
- Precision/scale normalization
- Type alias handling

#### Dependency Resolution

**Location**: `core/normalization/dependency_resolver.py`

Builds complete dependency graph and performs topological sorting:

```python
class DependencyResolver:
    def build_dependency_graph(
        self,
        objects: List[SqlObject]
    ) -> Dict[str, Set[str]]:
        """Build dependency graph for all objects"""
    
    def get_execution_order(
        self,
        objects: List[SqlObject]
    ) -> List[SqlObject]:
        """Return objects in dependency order"""
```

**Dependency Types**:
- Table dependencies (foreign keys, inheritance)
- View dependencies (base tables)
- Index dependencies (table columns)
- Procedure/Function dependencies
- Trigger dependencies

#### Identifier Normalization

**Location**: `core/normalization/identifier_normalizer.py`

Centralized identifier handling across SQL dialects:

```python
class IdentifierNormalizer:
    @staticmethod
    def normalize_identifier(
        dialect: str,
        identifier: str,
        quote_if_needed: bool = False
    ) -> str:
        """Normalize identifier according to dialect rules"""
    
    @staticmethod
    def normalize_qualified_name(
        dialect: str,
        schema: Optional[str],
        name: str
    ) -> str:
        """Generate schema-qualified name for dialect"""
```

**Features**:
- Dialect-specific quoting rules
- Case sensitivity handling
- Schema qualification
- Identifier comparison

### Round-Trip Testing

**Location**: `core/validation/round_trip_tester.py`

Automated testing framework for introspect → generate → execute → verify:

```python
class RoundTripTester:
    def __init__(
        self,
        source_provider: BaseProvider,
        test_provider: BaseProvider,
        source_schema: str,
        test_schema: str
    ):
        """Initialize round-trip tester"""
    
    def run_test(self) -> Dict[str, Any]:
        """
        Process:
        1. Introspect schema from source database
        2. Generate CREATE statements
        3. Execute on test database
        4. Re-introspect from test database
        5. Compare and verify
        """
```

**Use Cases**:
- Validate SQL generation accuracy
- Test introspection completeness
- Verify cross-database compatibility
- Automated regression testing

### Version Detection & Capability Matrix

**Location**: `db/introspection/version_detector.py`, `db/introspection/capability_matrix.py`

Detects database version and tracks feature availability:

```python
class VersionDetector:
    @staticmethod
    def detect_version(
        connection: Any,
        dialect: str
    ) -> DatabaseVersion:
        """Detect and parse database version"""
    
    @staticmethod
    def compare_versions(
        version1: DatabaseVersion,
        version2: DatabaseVersion
    ) -> int:
        """Compare two versions (-1, 0, 1)"""

class CapabilityMatrix:
    def is_feature_supported(
        self,
        dialect: str,
        feature: str,
        version: Optional[DatabaseVersion] = None
    ) -> bool:
        """Check if feature is supported for dialect/version"""
```

**Features**:
- Version parsing for all supported databases
- Feature requirement tracking
- Edition-specific capabilities
- Version comparison utilities

---

## SQL Generation & Diff-to-SQL

**Location**: `core/sql_generator/`

DBLift can generate SQL scripts from schema diffs, enabling automated schema synchronization. The system supports all major databases including CosmosDB with special handling for operations requiring Azure SDK.

### Diff-to-SQL Architecture

```python
class DiffSqlGenerator:
    def generate_from_diff(
        self,
        diff: SchemaDiff,
        expected_tables: Dict[str, Table],
        options: GenerationOptions
    ) -> List[SqlStatement]:
        """
        Generates SQL statements from schema differences:
        - CREATE statements for missing objects
        - ALTER statements for modified objects
        - DROP statements for extra objects
        """
```

### Supported Operations

| Operation | PostgreSQL | MySQL | SQL Server | Oracle | DB2 | CosmosDB |
|-----------|-----------|-------|------------|--------|-----|----------|
| CREATE TABLE | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (CREATE CONTAINER) |
| ALTER TABLE | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ (Schema-less, comments) |
| DROP TABLE | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ (Pseudo-SQL → SDK) |
| CREATE INDEX | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ (Indexing policy) |
| ALTER INDEX | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ (Indexing policy) |
| DROP INDEX | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ (Indexing policy) |

**Legend**: ✅ Full support | ⚠️ Special handling required

### CosmosDB Pseudo-SQL to Azure SDK Translation

**Location**: `core/sql_generator/cosmosdb_sdk_translator.py`

CosmosDB has unique requirements: some operations (like `DROP CONTAINER`) cannot be executed via SQL API and require Azure SDK. DBLift implements a **pseudo-SQL to SDK translator** that:

1. **Generates Pseudo-SQL**: Creates SQL-like statements that look like SQL but aren't executable
2. **Automatic Translation**: At execution time, translates pseudo-SQL to Azure SDK operations
3. **Python Script Generation**: Generates Python code for manual execution if needed

**Example Flow**:

```
SQL Generation
    ↓
Pseudo-SQL: "DROP CONTAINER my_container"
    ↓
Query Executor detects pseudo-SQL
    ↓
CosmosDbSdkTranslator translates to SDK operation
    ↓
Azure SDK: database.delete_container(container='my_container')
    ↓
Operation executed
```

**Key Components**:

```python
class CosmosDbSdkTranslator:
    def translate_to_sdk_operation(
        self, statement: SqlStatement
    ) -> Dict[str, Any]:
        """Convert pseudo-SQL to SDK operation dictionary"""
    
    def execute_sdk_operation(
        self, operation: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """Execute SDK operation via Azure SDK"""
    
    def generate_python_script(
        self, statements: List[SqlStatement]
    ) -> str:
        """Generate Python script for manual execution"""
```

**Supported SDK Operations**:

- **DROP CONTAINER** → `database.delete_container()`
- **ALTER CONTAINER** (throughput, indexing policy, TTL) → `container_client.replace_container()`
- **Future**: Indexing policy updates, partition key changes (where supported)

**Integration Points**:

1. **Query Executor** (`db/plugins/cosmosdb/cosmosdb/query_executor.py`):
   - Detects pseudo-SQL statements
   - Automatically translates and executes via SDK

2. **Script Formatter** (`core/sql_generator/script_formatter.py`):
   - Displays SDK operation hints in generated scripts
   - Shows Python code equivalents

3. **SqlStatement** (`core/sql_generator/sql_statement.py`):
   - Enhanced with `requires_sdk: bool` flag
   - Stores `sdk_operation: Dict[str, Any]` metadata

**Benefits**:

- ✅ **Actionable Scripts**: Generated SQL is executable, not just comments
- ✅ **Automatic Execution**: Pseudo-SQL translated and executed transparently
- ✅ **Manual Option**: Python scripts provided for manual execution
- ✅ **Clear Warnings**: Destructive operations clearly marked
- ✅ **Seamless Integration**: Works with existing execution flow

For detailed documentation, see [CosmosDB Pseudo-SQL Translator](COSMOSDB_PSEUDO_SQL_TRANSLATOR.md).

---

## Connection & Transaction Management

### Connection Ownership Pattern

**Key Principle**: Provider owns the connection, components receive it as a parameter.

```
┌─────────────────────────────────────────┐
│           Provider                      │
│                                         │
│  self.connection = ...                 │
│  self._in_transaction = False          │
│  self._transaction_depth = 0           │
│                                         │
│  ┌─────────────────────────────────┐  │
│  │  def execute_statement(sql):    │  │
│  │      return self.query_executor │  │
│  │          .execute(               │  │
│  │              self.connection, ← │──┼─ Connection passed explicitly
│  │              sql                │  │
│  │          )                      │  │
│  └─────────────────────────────────┘  │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│        QueryExecutor (Stateless)        │
│                                         │
│  def execute(self, connection, sql):   │
│      cursor = connection.cursor()      │
│      cursor.execute(sql)               │
│      return cursor.fetchall()          │
│                                         │
│  Note: NO self.connection stored       │
└─────────────────────────────────────────┘
```

### Why This Pattern?

**Problems with Stored Connections**:
```python
# ❌ OLD PATTERN (causes bugs)
class QueryExecutor:
    def __init__(self):
        self.connection = None  # Stored state

    def set_connection(self, connection):
        self.connection = connection  # Manual sync required

    def execute(self, sql):
        return self.connection.cursor()...  # May be stale!
```

**Issues**:
- Connection can become stale if Provider creates new connection
- Manual synchronization required (`executor.set_connection(new_conn)`)
- Race conditions in concurrent scenarios
- Unclear ownership

**Benefits of Explicit Passing**:
```python
# ✅ NEW PATTERN (safe and clear)
class QueryExecutor:
    def execute(self, connection, sql):  # Connection as parameter
        return connection.cursor()...
```

**Benefits**:
- ✅ No stale connections - always uses current
- ✅ No manual synchronization needed
- ✅ Thread-safe - no shared state
- ✅ Clear ownership - Provider owns connection
- ✅ Easy to test - just pass mock connection

### Auto-commit et sémantique transactionnelle par plugin

DBLift impose une sémantique de transaction explicite sur tous les plugins relationnels. Le tableau suivant résume le comportement transactionnel de chaque plugin :

| Plugin | API connexion | Auto-commit à la connexion | Modèle transactionnel | Begin / Commit / Rollback |
|--------|--------------|---------------------------|----------------------|--------------------------|
| PostgreSQL | SQLAlchemy (`psycopg`) | transaction SQLAlchemy | Commit/rollback explicite via Provider | `connection.commit()` / `connection.rollback()` via `BaseProvider` |
| MySQL | SQLAlchemy (`PyMySQL`) | transaction SQLAlchemy | Commit/rollback explicite via Provider | `connection.commit()` / `connection.rollback()` via `BaseProvider` |
| SQL Server | SQLAlchemy (`pymssql`) | transaction SQLAlchemy | Commit/rollback explicite via Provider | `connection.commit()` / `connection.rollback()` via `BaseProvider` |
| Oracle | SQLAlchemy (`python-oracledb`) | transaction SQLAlchemy | Commit/rollback explicite via Provider | `connection.commit()` / `connection.rollback()` via `BaseProvider` |
| DB2 | SQLAlchemy (`ibm_db_sa`) | transaction SQLAlchemy | Commit/rollback explicite via Provider | `connection.commit()` / `connection.rollback()` via `BaseProvider` |
| SQLite | sqlite3 (Python) | `isolation_level=None` | `BEGIN TRANSACTION` explicite en SQL | `BEGIN TRANSACTION` / `COMMIT` / `ROLLBACK` (SQL via `execute`) |
| CosmosDB | Azure SDK | N/A | Atomicité au niveau document/conteneur | N/A (pas de transaction ACID) |

#### Plugins SQLAlchemy (PostgreSQL, MySQL, SQL Server, Oracle, DB2)

Le contrôle transactionnel passe par `SqlAlchemyProvider` et la `Connection` SQLAlchemy. Cette configuration :
- Garantit que chaque migration s'exécute dans une transaction explicite
- Permet le rollback en cas d'échec via `BaseProvider.rollback_transaction()`
- Est redondante en `begin_transaction()` (défense en profondeur)

La gestion de la transaction est centralisée dans `BaseProvider` via `_in_transaction` et `_transaction_depth`.

#### SQLite (modèle différent)

SQLite utilise le module Python natif `sqlite3`. La connexion est créée avec `isolation_level=None`, ce qui place `sqlite3` en mode autocommit au niveau Python. Le contrôle transactionnel est assuré par des commandes SQL explicites (`BEGIN TRANSACTION`, `COMMIT`, `ROLLBACK`) émises par le `Provider`. Ce modèle est fonctionnellement équivalent au modèle SQLAlchemy : les migrations s'exécutent bien dans des transactions atomiques.

#### CosmosDB (sans transactions ACID)

CosmosDB est une base NoSQL (API Azure SDK). Il n'existe pas de concept `setAutoCommit`. Les opérations sur les documents sont atomiques au niveau de l'élément (document). Le locking migratoire est géré par concurrence optimiste via ETag. CosmosDB ne supporte pas les transactions multi-documents dans le modèle DBLift.

### Transaction State Management

Provider tracks transaction state to ensure safety:

```python
class BaseProvider:
    def __init__(self, config, log):
        self.connection = None
        self._in_transaction = False      # Are we in an active transaction?
        self._transaction_depth = 0       # Nested transaction counter

    def begin_transaction(self):
        """Start transaction"""
        if not self._in_transaction:
            if self.connection:
                self.connection.commit()  # Clear any pending
            self._in_transaction = True
            self._transaction_depth = 1
        else:
            self._transaction_depth += 1  # Nested transaction

    def commit_transaction(self):
        """Commit transaction"""
        self._transaction_depth -= 1
        if self._transaction_depth == 0:
            self.connection.commit()
            self._in_transaction = False

    def rollback_transaction(self):
        """Rollback transaction"""
        if self.connection:
            self.connection.rollback()
        self._in_transaction = False
        self._transaction_depth = 0

    def create_connection(self):
        """Create new connection and reset transaction state"""
        connection = self.connection_manager.create_connection()
        self.connection = connection

        # CRITICAL: Reset transaction state for fresh connection
        self._in_transaction = False
        self._transaction_depth = 0

        return connection
```

**Why Track Transaction State?**

1. **Nested Transactions**: Supports BEGIN inside BEGIN
2. **Safety Checks**: Prevents operations during transaction
3. **Clean State**: New connection starts with clean transaction state
4. **Debugging**: Can log transaction boundaries

### Connection Lifecycle

```
1. Provider Created
   ├─ connection = None
   ├─ _in_transaction = False
   └─ _transaction_depth = 0

2. First Operation
   └─ create_connection()
      ├─ connection = SQLAlchemy engine.connect()
      ├─ configure_connection()
      └─ return connection

3. Execute Migration
   ├─ begin_transaction()
   │  ├─ _in_transaction = True
   │  └─ _transaction_depth = 1
   │
   ├─ execute_statement(sql, ...) ──┐
   │                                 ├─→ query_executor.execute(self.connection, sql)
   │                                 └─→ SQL executed
   │
   ├─ history_manager.record(...) ──┐
   │                                 ├─→ history_manager.record(self.connection, ...)
   │                                 └─→ History recorded
   │
   └─ commit_transaction()
      ├─ _transaction_depth = 0
      ├─ connection.commit()
      └─ _in_transaction = False

4. Connection Lost (network issue)
   └─ create_connection()  ← Creates NEW connection
      ├─ connection = new SQLAlchemy connection
      ├─ _in_transaction = False      ← RESET
      └─ _transaction_depth = 0       ← RESET
```

---

## Testing Architecture

**Location**: `tests/`

DBLift has comprehensive test coverage across unit and integration tests.

### Test Structure

```
tests/
├── unit/                          # Fast, isolated tests
│   ├── api/                       # API client tests
│   ├── cli/                       # CLI tests
│   ├── config/                    # Configuration tests
│   ├── core/                      # Migration engine tests
│   │   ├── migration/
│   │   │   ├── commands/          # Command tests
│   │   │   ├── executor/          # Executor tests
│   │   │   └── snapshots/         # Snapshot tests
│   │   └── sql_parser/            # Parser tests
│   └── db/                        # Provider tests (mocked)
│
└── integration/                   # Real database tests
    ├── commands/                  # End-to-end command tests
    ├── comparison/                # Diff tests
    ├── concurrency/               # Concurrent migration tests
    ├── db/                        # Database-specific tests
    ├── features/                  # Feature tests
    ├── parsers/                   # Parser integration tests
    └── scenarios/                 # Real-world scenarios
```

### Testing Patterns

#### Unit Tests

Use mocks for database interactions:

```python
def test_migration_executor(mocker):
    # Mock provider
    mock_provider = mocker.Mock(spec=BaseProvider)
    mock_provider.execute_statement.return_value = []

    # Create executor
    executor = MigrationExecutor(
        config=test_config,
        provider=mock_provider,
        log=test_log
    )

    # Test operation
    result = executor.migrate()

    # Verify
    assert result.success
    mock_provider.execute_statement.assert_called()
```

#### Integration Tests

Use real databases via Docker containers:

```python
@pytest.fixture
def db_container():
    """Provides real PostgreSQL container"""
    container = PostgreSQLContainer("postgres:14")
    container.start()

    yield {
        "url": container.get_connection_url(),
        "username": container.username,
        "password": container.password,
        "schema": "public"
    }

    container.stop()

def test_migrate_real_database(db_container, tmp_path):
    # Create config
    config = create_config(tmp_path, db_container)

    # Create migration file
    (tmp_path / "migrations" / "V1__test.sql").write_text(
        "CREATE TABLE users (id INT PRIMARY KEY);"
    )

    # Execute migration
    client = DBLiftClient(config)
    result = client.migrate()

    # Verify in database
    assert result.success
    assert result.migrations_applied == 1
```

### Test Fixtures

**Location**: `tests/integration/conftest.py`

Key fixtures for integration tests:

```python
@pytest.fixture
def cleanup_database(db_container):
    """Clean database before and after each test"""
    config = create_config(db_container)
    client = DBLiftClient(config)
    provider = client.provider

    # Before test: Clean schema and history
    connection = provider.create_connection()
    provider.history_manager.delete_all_history(connection)
    provider.schema_operations.clean_schema(connection, schema)

    yield provider

    # After test: Clean up
    provider.schema_operations.clean_schema(connection, schema)
    provider.close_connection()
```

### Running Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Run integration tests for specific database
pytest tests/integration/ -k postgresql -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test
pytest tests/unit/core/migration/test_migration_executor.py::test_migrate_basic -v
```

---

## Adding New Database Support

To add support for a new database, implement these components.

> **Note**: For SDK-style databases, see the CosmosDB implementation (`db/plugins/cosmosdb/`) as a reference. For relational databases, prefer the `SqlAlchemyProvider` pattern used by PostgreSQL, MySQL, SQL Server, Oracle, and DB2.

### Step 1: Create Provider Directory

```
db/plugins/your_database/
├── __init__.py
├── provider.py                    # Main provider
└── your_database/
    ├── __init__.py
    ├── connection_manager.py
    ├── query_executor.py
    ├── schema_operations.py
    ├── locking_manager.py
    └── history_manager.py
```

### Step 2: Implement Provider

**db/plugins/your_database/provider.py**:

```python
from db.base_provider import BaseProvider

class YourDatabaseProvider(BaseProvider):
    def __init__(self, config: DbliftConfig, log: Logger):
        super().__init__(config, log)

        # Create components
        self.connection_manager = YourDatabaseConnectionManager(config, log)
        self.query_executor = YourDatabaseQueryExecutor(config, log)
        self.schema_operations = YourDatabaseSchemaOperations(config, log)
        self.locking_manager = YourDatabaseLockingManager(config, log)
        self.history_manager = YourDatabaseHistoryManager(config, log)

    def supports_transactional_ddl(self) -> bool:
        """Does database support DDL in transactions?"""
        return True  # or False
```

### Step 3: Implement Components

Each component follows its base class interface. Example:

**connection_manager.py**:
```python
from db.plugins.base_connection_manager import BaseConnectionManager

class YourDatabaseConnectionManager(BaseConnectionManager):
    def create_connection(self):
        # Database-specific connection logic
        pass

    def configure_connection(self, connection):
        # Set schema, isolation level, etc.
        pass
```

### Step 4: Register Provider

**db/provider_registry.py**:
```python
PROVIDERS = {
    "postgresql": "db.plugins.postgresql.provider.PostgresqlProvider",
    "mysql": "db.plugins.mysql.provider.MySqlProvider",
    # ... other databases
    "yourdatabase": "db.plugins.your_database.provider.YourDatabaseProvider",
}
```

### Step 5: Add Parser

**core/sql_parser/dialects/yourdatabase_config.py**:
```python
from core.sql_parser.base import BaseSqlParser

class YourDatabaseRegexParser(BaseSqlParser):
    def __init__(self):
        super().__init__(
            statement_delimiter=";",
            supports_dollar_quotes=False,
            batch_separator=None
        )

    def parse_script(self, sql: str) -> List[str]:
        # Parse SQL into statements
        pass
```

### Step 6: Add Tests

Create integration tests:

```python
# tests/integration/db/test_yourdatabase_integration.py
@pytest.fixture
def yourdatabase_container():
    # Setup Docker container
    pass

def test_migrate_yourdatabase(yourdatabase_container):
    # Test migration operations
    pass
```

### Step 7: Documentation

Update:
- README.md: Add to supported databases list
- Driver extra and SQLAlchemy URL example
- Configuration template example

---

## Summary

DBLift's architecture is designed for:

1. **Clarity**: Explicit dependencies, no hidden state
2. **Safety**: Transaction management, connection ownership
3. **Extensibility**: Easy to add new databases
4. **Testability**: Stateless components, dependency injection
5. **Maintainability**: Layered architecture, clear responsibilities

**Key Architectural Decisions**:

| Decision | Rationale |
|----------|-----------|
| Provider owns connection | Single source of truth, no synchronization needed |
| Components receive connection as parameter | Stateless, thread-safe, no stale references |
| 5-component provider pattern | Consistent structure across databases |
| Command pattern for operations | Isolated logic, easy to test |
| Factory pattern for creation | Centralized instantiation, consistent interfaces |
| Transaction state in provider | Safety checks, nested transaction support |

**For Developers**:
- Read the code in `api/client.py` to understand entry points
- Study `core/migration/executor/` for orchestration logic
- Review a SQLAlchemy provider implementation (e.g., `db/plugins/postgresql/`) to see component interaction
- Review SQLite or CosmosDB providers for non-SQLAlchemy implementation patterns
- Check `tests/integration/` for real-world usage examples
