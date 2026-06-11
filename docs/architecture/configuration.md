# Configuration System

**Location**: `config/`

Manages application settings from multiple sources.

## Configuration Structure

```python
@dataclass
class DbliftConfig:
    database: DatabaseConfig
    migrations: MigrationsConfig
    history_table: str = "dblift_schema_history"
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

## Configuration Loading

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

## YAML Configuration Example

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

logging:
  level: "INFO"
  format: "text"
```

## Environment Variables

All configuration options can be overridden via environment variables:

```bash
# Database configuration
export DBLIFT_DB_URL="postgresql+psycopg://localhost:5432/mydb"
export DBLIFT_DB_USERNAME="myuser"
export DBLIFT_DB_PASSWORD="mypassword"
export DBLIFT_DB_SCHEMA="public"
export DBLIFT_DB_TYPE="postgresql"

# Migration configuration
export DBLIFT_MIGRATIONS_DIRECTORY="./migrations"
export DBLIFT_MIGRATIONS_SCRIPT_ENCODING="utf-8"

# History
export DBLIFT_HISTORY_TABLE="dblift_schema_history"

# Logging
export DBLIFT_LOG_LEVEL="DEBUG"
export DBLIFT_LOG_FORMAT="json"
```

## Database-Specific Configuration

### SQLite

```yaml
database:
  type: "sqlite"
  path: "/path/to/database.db"  # Or ":memory:" for in-memory
  schema: "main"
```

### CosmosDB

```yaml
database:
  type: "cosmosdb"
  account_endpoint: "https://your-account.documents.azure.com:443/"
  account_key: "your-account-key"
  database_name: "your-database"
  # Or use managed identity:
  # use_managed_identity: true
```

## Validation

Configuration is validated on load:

- Database connection parameters are checked
- Migration directories are verified to exist
- Database type is validated
- Required fields are present

Use `dblift db validate-config` to check configuration without connecting.

## Related Documentation

- **[User Guide Configuration](../user-guide/configuration.md)** - User-facing configuration guide
- **[Architecture Overview](overview.md)** - How configuration is used
