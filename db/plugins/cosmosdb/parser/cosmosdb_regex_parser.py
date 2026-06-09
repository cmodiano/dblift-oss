"""CosmosDB SQL parser using regex-based approach.

CosmosDB SQL API uses T-SQL-like syntax but has special requirements:
- DML statements (DELETE, UPDATE, INSERT) can end without semicolons
- Statements are separated by newlines
- Uses SQL Server-like syntax for most operations
"""

import logging
from typing import List

from core.sql_parser.unified_regex_parser import RegexParser
from db.plugins.sqlserver.parser.parser_config import SqlServerConfig
from db.plugins.sqlserver.parser.sqlserver_regex_parser import SqlServerRegexParser

logger = logging.getLogger(__name__)


class CosmosDbRegexParser(SqlServerRegexParser):
    """
    CosmosDB parser using regex-based approach.

    Extends SqlServerRegexParser but uses CosmosDB-specific statement splitting
    that handles DML statements without semicolons.
    """

    def __init__(self) -> None:
        """Initialize CosmosDB regex parser."""
        # Call SqlServerRegexParser's __init__ to get SQL Server config setup
        # CosmosDB uses T-SQL-like syntax, so we inherit SQL Server parser behavior
        super().__init__()
        logger.debug("CosmosDB regex parser initialized")

    @property
    def dialect_name(self) -> str:
        """Return the dialect name."""
        return "cosmosdb"  # lint: allow-dialect-string: dialect dispatch

    def split_statements(self, sql_content: str, strict_tokenizer: bool = False) -> List[str]:
        """Split CosmosDB SQL content using CosmosDB-specific logic.

        CosmosDB allows DML statements (DELETE, UPDATE, INSERT) to end without
        semicolons. This method uses the CosmosDB-specific splitting logic
        from RegexParser.

        Args:
            sql_content: SQL content to split

        Returns:
            List of SQL statement strings
        """
        logger.debug(
            f"[ENTRY] CosmosDB split_statements called with input: {repr(sql_content[:100])}..."
        )

        if not sql_content.strip():
            return []

        # Use CosmosDB-specific splitting that handles statements without semicolons
        # This method is defined in RegexParser (unified_regex_parser.py)
        # Create a RegexParser instance and directly call the CosmosDB splitting method
        regex_parser = RegexParser(SqlServerConfig())  # type: ignore[no-untyped-call,arg-type]
        # Use the protected method directly since we know we want CosmosDB splitting
        return regex_parser._split_cosmosdb_statements(sql_content)
