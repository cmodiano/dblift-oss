"""Oracle dialect configuration for regex-based parsing.

This module provides Oracle/PL-SQL-specific patterns and configuration for the regex parser,
extracted from PLSQLParser.g4 and PLSQLLexer.g4 grammar files from grammars-v4 repository.
"""

import re
from typing import Dict, List, Pattern

from core.sql_parser.dialects.base_config import DialectConfig


class OracleConfig(DialectConfig):
    """Oracle dialect configuration extracted from PLSQLParser.g4 grammar.

    Grammar-based improvements include:
    - CREATE OR REPLACE support for all object types (VIEW, PROCEDURE, FUNCTION, PACKAGE, TRIGGER)
    - External tables (CREATE TABLE ... ORGANIZATION EXTERNAL)
    - Cluster tables (CREATE CLUSTER, CREATE TABLE ... CLUSTER)
    - Index-Organized Tables (CREATE TABLE ... ORGANIZATION INDEX)
    - Materialized views with refresh options
    - Function-based indexes
    - Domain indexes
    - Comprehensive synonym patterns
    - Database link operations
    """

    @property
    def name(self) -> str:
        """Dialect name."""
        return "oracle"  # lint: allow-dialect-string: dialect dispatch

    @property
    def batch_separators(self) -> List[Pattern[str]]:
        """Regex patterns for batch separators (slash for PL/SQL)."""
        return [re.compile(r"^\s*/\s*$", re.MULTILINE)]  # PL/SQL block terminator

    @property
    def quoted_identifiers(self) -> List[Pattern[str]]:
        """Regex patterns for quoted identifiers."""
        return [
            re.compile(r'"([^"]+)"'),  # Double-quoted identifiers "name"
        ]

    @property
    def comment_patterns(self) -> List[Pattern[str]]:
        """Regex patterns for comments."""
        return [
            re.compile(r"--.*$", re.MULTILINE),  # Line comments
            re.compile(r"/\*.*?\*/", re.DOTALL),  # Block comments
        ]

    @property
    def block_keywords(self) -> List[str]:
        """Keywords that start block statements.

        Oracle PL/SQL block statements that require special handling:
        - CREATE OR REPLACE PROCEDURE/FUNCTION/PACKAGE/TRIGGER
        - CREATE PROCEDURE/FUNCTION/PACKAGE/TRIGGER
        - DECLARE/BEGIN blocks
        """
        return [
            "CREATE OR REPLACE PROCEDURE",
            "CREATE PROCEDURE",
            "CREATE OR REPLACE FUNCTION",
            "CREATE FUNCTION",
            "CREATE OR REPLACE PACKAGE BODY",
            "CREATE PACKAGE BODY",
            "CREATE OR REPLACE PACKAGE",
            "CREATE PACKAGE",
            "CREATE OR REPLACE TRIGGER",
            "CREATE TRIGGER",
            "CREATE OR REPLACE VIEW",
            "ALTER VIEW",
            "DECLARE",
            "BEGIN",
        ]

    @property
    def ddl_patterns(self) -> Dict[str, Pattern[str]]:
        """DDL statement regex patterns extracted from PLSQLParser.g4.

        Grammar-based improvements:
        - CREATE OR REPLACE support for VIEW, PROCEDURE, FUNCTION, PACKAGE, TRIGGER
        - External tables (ORGANIZATION EXTERNAL)
        - Cluster tables (CLUSTER clause)
        - Index-Organized Tables (ORGANIZATION INDEX)
        - Materialized views with refresh options
        - Function-based indexes
        - Domain indexes
        - Comprehensive synonym patterns
        """
        # Identifier pattern for Oracle (supports $ and # characters)
        id_pattern = r'(?:"([^"]+)"|([a-zA-Z0-9_$#]+))'
        qualified_id = rf"(?:{id_pattern}\.)?{id_pattern}"

        return {
            # Table operations - Grammar-based: Supports ORGANIZATION EXTERNAL, ORGANIZATION INDEX, CLUSTER
            "create_table": re.compile(
                rf"CREATE\s+(?:GLOBAL\s+TEMPORARY\s+)?TABLE\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "alter_table": re.compile(
                rf"ALTER\s+TABLE\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_table": re.compile(
                rf"DROP\s+TABLE\s+{qualified_id}(?:\s+CASCADE\s+CONSTRAINTS)?",
                re.IGNORECASE,
            ),
            # View operations - Grammar-based: OR REPLACE support
            "create_view": re.compile(
                rf"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FORCE|NOFORCE\s+)?VIEW\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_view": re.compile(
                rf"DROP\s+VIEW\s+{qualified_id}(?:\s+CASCADE\s+CONSTRAINTS)?",
                re.IGNORECASE,
            ),
            # Materialized view operations - Grammar-based: Refresh options
            "create_materialized_view": re.compile(
                rf"CREATE\s+(?:OR\s+REPLACE\s+)?MATERIALIZED\s+VIEW\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_materialized_view": re.compile(
                rf"DROP\s+MATERIALIZED\s+VIEW\s+{qualified_id}",
                re.IGNORECASE,
            ),
            # Index operations - Grammar-based: BITMAP, function-based, domain indexes
            "create_index": re.compile(
                rf"CREATE\s+(?:UNIQUE\s+)?(?:BITMAP\s+)?INDEX\s+{qualified_id}\s+ON\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_index": re.compile(
                rf"DROP\s+INDEX\s+{qualified_id}",
                re.IGNORECASE,
            ),
            # Sequence operations
            "create_sequence": re.compile(
                rf"CREATE\s+SEQUENCE\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_sequence": re.compile(
                rf"DROP\s+SEQUENCE\s+{qualified_id}",
                re.IGNORECASE,
            ),
            # Procedure/Function operations - Grammar-based: OR REPLACE support
            "create_procedure": re.compile(
                rf"CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "create_function": re.compile(
                rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_procedure": re.compile(
                rf"DROP\s+PROCEDURE\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_function": re.compile(
                rf"DROP\s+FUNCTION\s+{qualified_id}",
                re.IGNORECASE,
            ),
            # Trigger operations - Grammar-based: OR REPLACE support
            "create_trigger": re.compile(
                rf"CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_trigger": re.compile(
                rf"DROP\s+TRIGGER\s+{qualified_id}",
                re.IGNORECASE,
            ),
            # Package operations - Grammar-based: OR REPLACE support
            "create_package": re.compile(
                rf"CREATE\s+(?:OR\s+REPLACE\s+)?PACKAGE\s+(?:BODY\s+)?{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_package": re.compile(
                rf"DROP\s+PACKAGE\s+(?:BODY\s+)?{qualified_id}",
                re.IGNORECASE,
            ),
            # Synonym operations - Grammar-based: OR REPLACE, PUBLIC support
            "create_synonym": re.compile(
                rf"CREATE\s+(?:OR\s+REPLACE\s+)?(?:PUBLIC\s+)?SYNONYM\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_synonym": re.compile(
                rf"DROP\s+(?:PUBLIC\s+)?SYNONYM\s+{qualified_id}",
                re.IGNORECASE,
            ),
            # Database Link operations - Grammar-based: PUBLIC support
            "create_database_link": re.compile(
                rf"CREATE\s+(?:PUBLIC\s+)?DATABASE\s+LINK\s+{id_pattern}",
                re.IGNORECASE,
            ),
            "drop_database_link": re.compile(
                rf"DROP\s+(?:PUBLIC\s+)?DATABASE\s+LINK\s+{id_pattern}",
                re.IGNORECASE,
            ),
            # Cluster operations
            "create_cluster": re.compile(
                rf"CREATE\s+CLUSTER\s+{qualified_id}",
                re.IGNORECASE,
            ),
            "drop_cluster": re.compile(
                rf"DROP\s+CLUSTER\s+{qualified_id}",
                re.IGNORECASE,
            ),
            # Other DDL
            "truncate_table": re.compile(
                rf"TRUNCATE\s+TABLE\s+{qualified_id}(?:\s+(?:DROP\s+)?(?:REUSE\s+)?STORAGE)?",
                re.IGNORECASE,
            ),
        }

    @property
    def dml_patterns(self) -> Dict[str, Pattern[str]]:
        """DML statement regex patterns."""
        return {
            "insert": re.compile(
                r'INSERT\s+(?:INTO\s+)?(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
            "update": re.compile(
                r'UPDATE\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
            "delete": re.compile(
                r'DELETE\s+(?:FROM\s+)?(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
            "merge": re.compile(
                r'MERGE\s+(?:INTO\s+)?(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
            "call": re.compile(
                r'CALL\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
        }

    @property
    def query_patterns(self) -> Dict[str, Pattern[str]]:
        """Query statement regex patterns."""
        return {
            "select": re.compile(r"SELECT\s+", re.IGNORECASE),
            "with": re.compile(r"WITH\s+", re.IGNORECASE),
        }

    @property
    def object_patterns(self) -> Dict[str, Pattern[str]]:
        """Object extraction regex patterns based on Oracle parser patterns."""
        return {
            # Tables - captures both quoted and unquoted identifiers with schema
            "table_create": re.compile(
                r'CREATE\s+TABLE\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
            "table_alter": re.compile(
                r'ALTER\s+TABLE\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
            "table_drop": re.compile(
                r'DROP\s+TABLE\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
            # Views
            "view_create": re.compile(
                r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
            # Sequences
            "sequence_create": re.compile(
                r'CREATE\s+SEQUENCE\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
            # Indexes - complex pattern that captures index name, schema, table, and columns
            "index_create": re.compile(
                r'CREATE\s+(?:UNIQUE\s+)?(?:BITMAP\s+)?INDEX\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\s+ON\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\s*\(\s*([^)]+)\s*\)',
                re.IGNORECASE,
            ),
            # Procedures and Functions
            "procedure_create": re.compile(
                r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION)\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
            # Triggers
            "trigger_create": re.compile(
                r'CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+(?:(?:"([^"]+)"|([a-zA-Z0-9_$#]+))\.)?(?:"([^"]+)"|([a-zA-Z0-9_$#]+))',
                re.IGNORECASE,
            ),
        }

    def get_default_schema(self) -> str:
        """Get default schema name for Oracle."""
        return "DEFAULT_SCHEMA"  # Oracle doesn't have a standard default like SQL Server's dbo

    def get_identifier_pattern(self) -> Pattern[str]:
        """Get regex pattern for Oracle identifiers.

        Grammar-based: Oracle identifiers can contain:
        - Letters (a-z, A-Z)
        - Digits (0-9)
        - Underscore (_)
        - Dollar sign ($)
        - Hash (#)
        - Quoted identifiers preserve case and can contain any characters
        """
        return re.compile(r'(?:"([^"]+)"|([a-zA-Z0-9_$#]+))', re.IGNORECASE)

    def get_qualified_identifier_pattern(self) -> Pattern[str]:
        """Get regex pattern for qualified identifiers (schema.object).

        Grammar-based: Oracle supports schema-qualified identifiers with quoted/unquoted support.
        """
        identifier_pattern = r'(?:"([^"]+)"|([a-zA-Z0-9_$#]+))'
        return re.compile(rf"(?:{identifier_pattern}\.)?{identifier_pattern}", re.IGNORECASE)

    def normalize_identifier(self, identifier: str, is_quoted: bool = False) -> str:
        """Normalize identifier according to Oracle rules.

        Grammar-based Oracle rules:
        - Unquoted identifiers become uppercase
        - Quoted identifiers preserve case exactly
        - Identifiers can contain $ and # characters
        """
        if is_quoted:
            return identifier  # Preserve exact case for quoted identifiers
        else:
            return identifier.upper()  # Oracle converts unquoted identifiers to uppercase
