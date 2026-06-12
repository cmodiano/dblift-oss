"""
Placeholder management for migration executor.

This module handles initialization and replacement of placeholders in SQL scripts.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from core.migration.placeholders.placeholder_service import PlaceholderService

from config import DbliftConfig
from core.logger import Log, NullLog


class PlaceholderManager:
    """Manages placeholders for SQL migration scripts."""

    def __init__(self, config: DbliftConfig, log: Log, executor: Optional[Any] = None):
        """Initialize the placeholder manager.

        Args:
            config: Application configuration
            log: Logger instance
            executor: The migration executor (for getting installed_by)
        """
        self.config = config
        self.log = log if log is not None else NullLog()
        self.executor = executor
        self.placeholder_service: Optional["PlaceholderService"] = None  # Will be set by executor

    def init_placeholders(self) -> Dict[str, Any]:
        """Initialize placeholders dictionary with both default and user-defined placeholders.

        Returns:
            Dictionary of placeholders and their values
        """
        placeholders = {
            # Default system placeholders with dblift_ prefix
            "dblift_schema": self.config.database.schema,
            "dblift_database": getattr(
                self.config.database,
                "database",
                getattr(
                    self.config.database,
                    "database_name",
                    getattr(self.config.database, "host", None),
                ),
            ),
            "dblift_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "dblift_date": datetime.now().strftime("%Y-%m-%d"),
            "dblift_time": datetime.now().strftime("%H:%M:%S"),
            "dblift_username": (
                self.executor.get_installed_by() if self.executor else self.config.database.username
            ),
        }
        # Add user-defined placeholders if present
        if hasattr(self.config, "placeholders") and self.config.placeholders:
            placeholders.update(self.config.placeholders)
        return placeholders
