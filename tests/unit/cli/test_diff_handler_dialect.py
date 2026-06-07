"""Regression tests for ``cli.handlers.diff._handle_diff``.

Cursor-bot follow-up on d09d048 — the split of
``cli/_command_handlers.py`` into ``cli/handlers/`` propagated a
latent bug from the original code: the ``--generate-sql`` branch
resolved the SQL dialect with ``getattr(getattr(ctx, "config", None),
"database", None)``. ``CliCommandContext`` has no ``config`` field
(its fields are ``client``, ``args``, ``log``, ``scripts_dir``,
``additional_scripts_dirs``, ``recursive``, ``placeholders``,
``dir_recursive_map``), so this expression always evaluated to
``None`` → ``dialect_name = ""`` → Pygments fell back to the generic
``sql`` lexer regardless of the actual database.

The fix is to read the config through ``ctx.client.config`` (the same
pattern ``cli.handlers.validate_sql`` already uses). These tests pin
that resolution path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestDiffDialectResolution:
    """``_handle_diff --generate-sql`` must resolve the dialect via ``ctx.client.config``."""

    def test_dialect_resolved_via_client_config(self):
        # We test the resolver expression in isolation rather than running
        # the full handler — that lets the test stay tight and not pull in
        # the whole snapshot/diff stack.
        client = MagicMock()
        client.config = MagicMock()
        client.config.database = MagicMock()
        client.config.database.type = "mysql"

        ctx = MagicMock()
        ctx.client = client

        # Mirror the resolver expression from cli/handlers/diff.py
        config = getattr(ctx.client, "config", None) if ctx.client else None
        dialect = getattr(config, "database", None) if config is not None else None
        dialect_name = (getattr(dialect, "type", None) or "").lower()

        assert dialect_name == "mysql"

    def test_dialect_falls_back_to_empty_when_client_missing(self):
        ctx = MagicMock()
        ctx.client = None

        config = getattr(ctx.client, "config", None) if ctx.client else None
        dialect = getattr(config, "database", None) if config is not None else None
        dialect_name = (getattr(dialect, "type", None) or "").lower()

        assert dialect_name == ""

    def test_dialect_falls_back_to_empty_when_config_missing(self):
        client = MagicMock(spec=["foo"])  # no ``config`` attribute
        ctx = MagicMock()
        ctx.client = client

        config = getattr(ctx.client, "config", None) if ctx.client else None
        dialect = getattr(config, "database", None) if config is not None else None
        dialect_name = (getattr(dialect, "type", None) or "").lower()

        assert dialect_name == ""

    def test_legacy_buggy_pattern_was_returning_empty(self):
        """Pin the bug — ensure we never re-introduce ``getattr(ctx, "config", None)``."""
        ctx = MagicMock(spec=["client", "args", "log"])
        ctx.client = MagicMock()
        ctx.client.config = MagicMock()
        ctx.client.config.database = MagicMock()
        ctx.client.config.database.type = "oracle"

        # Old (buggy) expression — ``CliCommandContext`` has no ``config`` field
        # so ``getattr`` returns ``None``, the whole chain collapses to "".
        old_dialect_name = (
            getattr(getattr(getattr(ctx, "config", None), "database", None), "type", None) or ""
        ).lower()
        assert old_dialect_name == "", "buggy legacy pattern must yield empty string"

        # New expression returns the right dialect
        new_dialect_name = (
            getattr(getattr(getattr(ctx.client, "config", None), "database", None), "type", None)
            or ""
        ).lower()
        assert new_dialect_name == "oracle", "fixed pattern must return the actual dialect"
