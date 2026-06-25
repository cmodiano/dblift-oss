"""Parsing helpers for CosmosDB pseudo-SQL."""

from __future__ import annotations

import re
from typing import Iterable, Optional

_CONTAINER_IDENTIFIER = r'(?P<name>"[^"]+"|`[^`]+`|\[[^\]]+\]|[^\s(;,.]+)'


def extract_container_name(
    sql: str,
    verbs: Iterable[str],
    *,
    allow_if_exists: bool = False,
    allow_if_not_exists: bool = False,
) -> Optional[str]:
    """Extract the container name after ``<verb> CONTAINER``.

    CosmosDB pseudo-DDL allows Flyway-style guard clauses in places where the
    SDK call is already idempotent. Consume those clauses before reading the
    identifier so ``IF`` is not mistaken for the container name.
    """
    sql_no_comments = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    sql_no_comments = re.sub(r"/\*.*?\*/", "", sql_no_comments, flags=re.DOTALL)

    escaped_verbs = "|".join(re.escape(verb) for verb in verbs)
    optional_clauses = []
    if allow_if_not_exists:
        optional_clauses.append(r"IF\s+NOT\s+EXISTS")
    if allow_if_exists:
        optional_clauses.append(r"IF\s+EXISTS")

    clause_pattern = ""
    if optional_clauses:
        clause_pattern = rf"(?:(?:{'|'.join(optional_clauses)})\s+)?"

    match = re.search(
        rf"\b(?:{escaped_verbs})\s+CONTAINER\s+{clause_pattern}{_CONTAINER_IDENTIFIER}",
        sql_no_comments,
        re.IGNORECASE,
    )
    if not match:
        return None

    name = match.group("name").rstrip(";.,")
    # Strip surrounding quote delimiters: "name", `name`, [name]
    if len(name) >= 2:
        if (name[0] == '"' and name[-1] == '"') or (name[0] == "`" and name[-1] == "`"):
            name = name[1:-1]
        elif name[0] == "[" and name[-1] == "]":
            name = name[1:-1]
    return name
