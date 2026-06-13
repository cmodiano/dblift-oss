"""DialectQuirks implementation for {{cookiecutter.dialect_name}}.

Override only the hooks that differ from BaseQuirks defaults.
See db/base_quirks.py and docs/development/adding-database-support.md
for the full hook catalogue.
"""

from __future__ import annotations

from typing import Any, Optional, Type

from db.base_quirks import BaseQuirks


class {{cookiecutter.dialect_name.capitalize()}}Quirks(BaseQuirks):
    """Quirks for {{cookiecutter.dialect_name}}.

    Fill in capability flags and hook implementations as needed.
    """

    # --- Capability matrix (examples; change to match your DB) ----------------
    supports_transactions = True
    supports_transactional_ddl = True
    schema_required = False
    uppercase_identifiers = False
    clean_strategy = "native"

    # sqlglot (if applicable)
    sqlglot_dialect = None

    # quoting
    quote_open = '"'
    quote_close = '"'

    def __init__(self, dialect_name: str = "{{cookiecutter.dialect_name}}") -> None:
        super().__init__(dialect_name=dialect_name)

    # --- Generator hooks (return None to use no OSS generator)
    def ddl_generator_class(self) -> None:
        """OSS builds do not ship SQL generator implementations."""
        return None

    def alter_generator_class(self) -> None:
        """OSS builds do not ship ALTER generator implementations."""
        return None
