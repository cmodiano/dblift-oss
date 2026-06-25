"""
Identifier normalization for SQL objects.

Provides centralized handling of identifier normalization across databases,
handling case sensitivity, quoted vs unquoted identifiers, and preserving
original names for SQL generation.
"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple

logger = None  # Will be set if logging is needed


@dataclass
class NormalizedIdentifier:
    """Represents a normalized identifier with original preserved."""

    normalized: str  # Lowercase, unquoted canonical form
    original: str  # Original identifier as provided
    was_quoted: bool = False  # Whether original was quoted
    case_sensitive: bool = False  # Whether case should be preserved

    def __str__(self) -> str:
        """Return normalized form."""
        return self.normalized

    def to_sql(self, dialect: str, force_quotes: bool = False) -> str:
        """Convert to SQL format for given dialect.

        Args:
            dialect: Target SQL dialect
            force_quotes: Force quoting even if not needed

        Returns:
            SQL-formatted identifier
        """
        if force_quotes or self.was_quoted or self.case_sensitive:
            # When case-sensitive, preserve original casing:
            # - If was_quoted: normalized already contains unquoted value with correct case
            # - If not quoted: original has the correct case without quotes
            if self.case_sensitive:
                identifier = self.normalized if self.was_quoted else self.original
            else:
                identifier = self.normalized
            return self._quote_for_dialect(dialect, identifier)
        return self.normalized

    def _quote_for_dialect(self, dialect: str, identifier: str) -> str:
        """Quote identifier according to dialect rules.

        Story 26-9: quote characters come from plugin Quirks
        (``quote_open`` / ``quote_close``) instead of a local table.
        """
        from db.provider_registry import ProviderRegistry

        quirks = ProviderRegistry.get_quirks((dialect or "").lower())
        return f"{quirks.quote_open}{identifier}{quirks.quote_close}"


class IdentifierNormalizer:
    """
    Normalizes SQL identifiers across databases.

    Handles:
    - Case sensitivity rules per database
    - Quoted vs unquoted identifiers
    - Schema-qualified names
    - Preserving original for SQL generation
    """

    def __init__(self, dialect: str = ""):
        """
        Initialize the identifier normalizer.

        Args:
            dialect: Database dialect
        """
        from db.provider_registry import ProviderRegistry

        self.dialect = dialect.lower()
        # Story 26-9: case-folding rule comes from plugin Quirks
        # (``unquoted_identifier_case``). Quoted identifiers always
        # preserve case — that's the SQL standard.
        quirks = ProviderRegistry.get_quirks(self.dialect)
        self.case_rules = {
            "unquoted": quirks.unquoted_identifier_case,
            "quoted": "preserve",
        }

    def normalize(self, identifier: str, preserve_case: bool = False) -> NormalizedIdentifier:
        """
        Normalize an identifier to canonical form.

        Args:
            identifier: Identifier to normalize
            preserve_case: Whether to preserve original case

        Returns:
            NormalizedIdentifier object
        """
        if not identifier:
            return NormalizedIdentifier(normalized="", original=identifier)

        original = identifier
        was_quoted = self._is_quoted(identifier)

        # Remove quotes if present
        if was_quoted:
            identifier = self._unquote(identifier)
            case_sensitive = True  # Quoted identifiers are case-sensitive
        else:
            case_sensitive = preserve_case

        # Normalize case based on dialect rules
        if was_quoted:
            # Quoted: preserve case
            normalized = identifier
        else:
            # Unquoted: apply dialect-specific case rules
            case_rule = self.case_rules.get("unquoted", "lowercase")
            if case_rule == "uppercase":
                normalized = identifier.upper()
            elif case_rule == "lowercase":
                normalized = identifier.lower()
            elif case_rule == "case_insensitive":
                normalized = identifier.lower()  # Use lowercase as canonical
            else:
                normalized = identifier  # preserve

        return NormalizedIdentifier(
            normalized=normalized,
            original=original,
            was_quoted=was_quoted,
            case_sensitive=case_sensitive,
        )

    def normalize_qualified_name(
        self,
        qualified_name: str,
        default_schema: Optional[str] = None,
    ) -> Tuple[NormalizedIdentifier, Optional[NormalizedIdentifier]]:
        """
        Normalize a schema-qualified name (e.g., "schema.table").

        Args:
            qualified_name: Qualified name (schema.object or just object)
            default_schema: Default schema if not specified

        Returns:
            Tuple of (schema_normalized, object_normalized)
        """
        if "." in qualified_name:
            parts = qualified_name.split(".", 1)
            schema_part: Optional[str] = parts[0]
            object_part = parts[1]
        else:
            schema_part = default_schema
            object_part = qualified_name

        schema_norm = self.normalize(schema_part) if schema_part else None
        object_norm = self.normalize(object_part)

        return (object_norm, schema_norm)

    def denormalize(
        self,
        normalized: NormalizedIdentifier,
        dialect: Optional[str] = None,
        force_quotes: bool = False,
    ) -> str:
        """
        Convert normalized identifier back to SQL format.

        Args:
            normalized: NormalizedIdentifier to convert
            dialect: Target dialect (uses instance dialect if not provided)
            force_quotes: Force quoting even if not needed

        Returns:
            SQL-formatted identifier string
        """
        target_dialect = dialect or self.dialect
        return normalized.to_sql(target_dialect, force_quotes)

    def _quote_chars(self) -> Tuple[str, str]:
        """Resolve (open, close) quote chars from the dialect's quirks."""
        from db.provider_registry import ProviderRegistry

        q = ProviderRegistry.get_quirks(self.dialect)
        return (q.quote_open, q.quote_close)

    def _is_quoted(self, identifier: str) -> bool:
        """Check if identifier is quoted.

        Story 26-5 / PR #241 Bugbot: NoSQL plugins (CosmosDB) declare
        ``quote_open=""``/``quote_close=""`` to opt out of identifier
        quoting. ``str.startswith("")`` returns ``True`` for every
        string, so we must guard against empty quote characters here —
        otherwise every identifier would be flagged as quoted and
        ``_unquote`` would mangle it into the empty string.
        """
        if not identifier:
            return False
        open_q, close_q = self._quote_chars()
        if not open_q or not close_q:
            return False
        return identifier.startswith(open_q) and identifier.endswith(close_q)

    def _unquote(self, identifier: str) -> str:
        """Remove quotes from identifier."""
        if not self._is_quoted(identifier):
            return identifier
        open_q, close_q = self._quote_chars()
        # ``_is_quoted`` already rejected empty quote chars, so the
        # slice is safe (``-len(close_q) < 0``).
        return identifier[len(open_q) : -len(close_q)]

    def compare_identifiers(
        self,
        id1: str,
        id2: str,
        case_sensitive: bool = False,
    ) -> bool:
        """
        Compare two identifiers for equality.

        Args:
            id1: First identifier
            id2: Second identifier
            case_sensitive: Whether comparison should be case-sensitive

        Returns:
            True if identifiers are equal
        """
        norm1 = self.normalize(id1)
        norm2 = self.normalize(id2)

        if case_sensitive:
            return norm1.original == norm2.original

        return norm1.normalized == norm2.normalized

    @classmethod
    def get_quote_chars(cls, dialect: str) -> Tuple[str, str]:
        """Get quote characters for a dialect (delegates to plugin Quirks)."""
        from db.provider_registry import ProviderRegistry

        q = ProviderRegistry.get_quirks((dialect or "").lower())
        return (q.quote_open, q.quote_close)

    @classmethod
    def should_quote(cls, identifier: str, dialect: str) -> bool:
        """
        Determine if an identifier should be quoted.

        Args:
            identifier: Identifier to check
            dialect: Database dialect

        Returns:
            True if identifier should be quoted
        """
        # Quote if contains special characters, spaces, or is a reserved word
        if not identifier:
            return False

        # Check for special characters
        if re.search(r"[^a-zA-Z0-9_]", identifier):
            return True

        # Check for reserved words (basic check)
        reserved_words = {
            "select",
            "from",
            "where",
            "insert",
            "update",
            "delete",
            "create",
            "alter",
            "drop",
            "table",
            "view",
            "index",
            "schema",
            "database",
            "user",
            "order",
            "group",
            "by",
        }
        if identifier.lower() in reserved_words:
            return True

        return False
