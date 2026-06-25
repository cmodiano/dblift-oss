"""
Centralized object naming conventions per database dialect.

This module provides the single source of truth for how object names
(table, schema, etc.) should be standardized for each database type,
according to their default naming conventions.
"""

# Databases that store unquoted identifiers as UPPERCASE
UPPERCASE_DIALECTS = frozenset({"oracle", "db2"})

# Databases that store unquoted identifiers as lowercase (or are case-insensitive)
LOWERCASE_DIALECTS = frozenset({"postgresql", "sqlserver", "mysql", "sqlite", "cosmosdb"})


def get_normalized_object_name(object_name: str, dialect: str) -> str:
    """Return the correct object name for the given database dialect.

    Each database has a default convention for unquoted identifiers:
    - Oracle, DB2: UPPERCASE
    - PostgreSQL, SQL Server, MySQL, SQLite, CosmosDB: lowercase
    - Unknown dialects: lowercase (safe default)

    Use this function whenever you need to resolve object names for
    database operations (e.g. history table, lock table) to ensure
    the correct case is used.

    Args:
        object_name: Base object name (e.g., "dblift_schema_history")
        dialect: Database dialect (oracle, postgresql, sqlserver, mysql, db2, sqlite, cosmosdb)

    Returns:
        Object name with appropriate case for the database dialect
    """
    dialect_lower = dialect.lower() if dialect else ""

    if dialect_lower in UPPERCASE_DIALECTS:
        return object_name.upper()
    return object_name.lower()
