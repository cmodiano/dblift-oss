"""
Migration classification utilities.

This module provides utilities for classifying and formatting migration
categories and types for display purposes.
"""

from typing import Any, Optional, Tuple

from core.logger import Log
from core.migration.migration import VERSIONED_SCRIPT_TYPES


class MigrationClassifier:
    """Classifies and formats migration categories and types."""

    def __init__(self, logger: Log):
        """Initialize the migration classifier.

        Args:
            logger: Logger instance for debugging
        """
        self.logger = logger

    def get_category_and_type(
        self, m_type: str, migration: Optional[Any] = None
    ) -> Tuple[str, str]:
        """Get the category and display type for a migration.

        Args:
            m_type: Migration type string
            migration: Optional migration object to extract additional info

        Returns:
            Tuple of (category, display_type)
        """
        if not m_type:
            return ("Unknown", "Unknown")

        m_type_upper = m_type.upper()

        if m_type_upper in VERSIONED_SCRIPT_TYPES:
            return ("Versioned", "Versioned")
        elif m_type_upper == "REPEATABLE":
            return ("Repeatable", "Repeatable")
        elif m_type_upper == "UNDO_SQL":
            return ("Undo", "Undo SQL")
        elif m_type_upper == "BASELINE":
            return ("Baseline", "Baseline")
        elif m_type_upper == "DELETE":
            # For DELETE entries, try to extract original type from migration
            if migration:
                description = getattr(migration, "description", "")
                if description and "[DELETE:" in description:
                    try:
                        start = description.index("[DELETE:") + 8
                        end = description.index("]", start)
                        original_type = description[start:end].strip()

                        # Map to display category
                        if original_type in VERSIONED_SCRIPT_TYPES:
                            return ("Versioned", "Versioned")
                        elif original_type == "REPEATABLE":
                            return ("Repeatable", "Repeatable")
                        elif original_type == "UNDO_SQL":
                            return ("Undo", "Undo SQL")
                    except (ValueError, IndexError):
                        pass

                # Fallback: infer from script name
                script_name = getattr(migration, "script_name", "")
                if script_name.startswith("V"):
                    return ("Versioned", "Versioned")
                elif script_name.startswith("R"):
                    return ("Repeatable", "Repeatable")
                elif script_name.startswith("U"):
                    return ("Undo", "Undo SQL")

            return ("Deleted", "Deleted")
        else:
            # Format unknown types nicely
            formatted = self._format_category(m_type)
            return (formatted, formatted)

    def _format_category(self, category: str) -> str:
        """Format category string with proper capitalization.

        Args:
            category: Category string to format

        Returns:
            Formatted category string
        """
        if not category:
            return ""
        return category[0].upper() + category[1:].lower()
