"""MariaDB native provider."""

from __future__ import annotations

from db.plugins.mysql.provider import MySqlProvider


class MariadbProvider(MySqlProvider):
    """MariaDB-specific native provider."""

    canonical_dialect_key = "mariadb"


__all__ = ["MariadbProvider"]
