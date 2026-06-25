"""Per-command CLI handler package.

Each module in this package implements one ``_handle_<command>`` function
plus its directly-related helpers. Shared infrastructure (the
``CliCommandContext`` dataclass, the ``_extract_version_filters`` helper,
etc.) lives in :mod:`cli.handlers._shared`.

The legacy single-module ``cli._command_handlers`` is kept as a thin
re-export shim so existing imports (``cli.main`` and the test suite)
keep working unchanged.
"""
