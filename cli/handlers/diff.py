"""Handler for the ``diff`` command."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from cli.handlers._shared import (
    CliCommandContext,
    _extract_version_filters,
    _set_command_completed,
)


def _validate_output_file_flag(ctx: CliCommandContext) -> bool:
    """Return False (and log) if ``--output-file`` was passed without ``--generate-sql``."""
    if (
        hasattr(ctx.args, "output_file")
        and ctx.args.output_file
        and not getattr(ctx.args, "generate_sql", False)
    ):
        ctx.log.error("--output-file requires --generate-sql flag")
        return False
    return True


def _resolve_filter_lists(
    ctx: CliCommandContext,
) -> Tuple[
    Optional[str],
    Optional[List[str]],
    Optional[List[str]],
    Optional[List[str]],
    Optional[List[str]],
]:
    """Parse the version/tag filter args from ``ctx.args`` and return list forms.

    Also warns when ``--versions``/``--exclude-versions`` are supplied — those
    filters don't affect snapshot-based diff.
    """
    target_version, versions, exclude_versions, tags, exclude_tags = _extract_version_filters(
        ctx.args
    )

    if versions or exclude_versions:
        ctx.log.warning(
            "Note: --versions and --exclude-versions filters do not affect the database snapshot used for diff. "
            "The snapshot contains the complete schema from all applied migrations. "
            "To compare against a specific version, use --snapshot-model with a versioned snapshot file."
        )

    tags_list = tags.split(",") if tags else None
    exclude_tags_list = exclude_tags.split(",") if exclude_tags else None
    versions_list = versions.split(",") if versions else None
    exclude_versions_list = exclude_versions.split(",") if exclude_versions else None
    return target_version, tags_list, exclude_tags_list, versions_list, exclude_versions_list


def _build_expected_objects(result: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    """Build the ``expected_objects`` dict from ``result.expected_payload`` for SQL generation.

    Returns ``None`` when no expected payload is attached (the SQL generator
    falls back to introspection-only mode).
    """
    if not (hasattr(result, "expected_payload") and result.expected_payload):
        return None

    def build_dict(objects_list: Any) -> Dict[str, Any]:
        """Convert list of objects to dict keyed by name."""
        if not objects_list:
            return {}
        result_dict: Dict[str, Any] = {}
        for obj in objects_list:
            name = getattr(obj, "name", None)
            if name:
                result_dict[str(name)] = obj
        return result_dict

    payload = result.expected_payload
    return {
        "tables": build_dict(payload.tables),
        "views": build_dict(payload.views),
        "indexes": build_dict(payload.indexes),
        "sequences": build_dict(payload.sequences),
        "triggers": build_dict(payload.triggers),
        "procedures": build_dict(payload.procedures),
        "functions": build_dict(payload.functions),
        "synonyms": build_dict(payload.synonyms),
        "extensions": build_dict(payload.extensions),
        "user_defined_types": build_dict(payload.user_defined_types),
        "packages": build_dict(payload.packages),
        "events": build_dict(payload.events),
        "database_links": build_dict(payload.database_links),
        "linked_servers": build_dict(payload.linked_servers),
        "foreign_data_wrappers": build_dict(payload.foreign_data_wrappers),
        "foreign_servers": build_dict(payload.foreign_servers),
    }


def _resolve_pygments_lexer(ctx: CliCommandContext) -> str:
    """Resolve the Pygments lexer name for the client's dialect.

    Falls back to ``"sql"`` for any of: missing config, unregistered dialect,
    unknown Pygments lexer (CliCommandContext has no ``config`` field — it
    carries ``client`` and config lives on ``client.config``).
    """
    from api._cli_support import ProviderRegistry

    config = getattr(ctx.client, "config", None) if ctx.client else None
    dialect = getattr(config, "database", None) if config is not None else None
    dialect_name = (getattr(dialect, "type", None) or "").lower()
    try:
        pygments_lexer = ProviderRegistry.get_quirks(dialect_name).pygments_lexer
        import pygments.lexers

        pygments.lexers.get_lexer_by_name(pygments_lexer)
        return str(pygments_lexer)
    except Exception:
        return "sql"


def _render_sql_script(ctx: CliCommandContext, sql_script: str) -> None:
    """Print ``sql_script`` to the console (syntax-highlighted) and the file log (raw)."""
    if not sql_script.strip():
        ctx.log.info(sql_script)
        return

    from rich.syntax import Syntax

    pygments_lexer = _resolve_pygments_lexer(ctx)
    # Console gets syntax-highlighted SQL; file/JSON/HTML logs get the raw
    # text via file_only_info to avoid ANSI/markup leaking to non-console sinks.
    ctx.log.console_print(Syntax(sql_script, pygments_lexer, theme="monokai", line_numbers=False))
    ctx.log.file_only_info(sql_script)


def _generate_and_render_sql(ctx: CliCommandContext, result: Any) -> None:
    """Generate SQL from the diff result and emit it to the configured sinks.

    Mutates ``result`` on failure (``success = False``, error message set).
    """
    output_file = getattr(ctx.args, "output_file", None)
    ctx.log.info(f"Generating SQL script{f' to {output_file}' if output_file else ''}...")

    expected_objects = _build_expected_objects(result)

    try:
        sql_result = ctx.client.generate_sql_from_diff(
            diff_result=result,
            output_file=output_file,
            expected_objects=expected_objects,
            title="Schema Synchronization Script",
            description="Generated by dblift diff --generate-sql",
            include_comments=True,
            include_checks=True,
        )
    except Exception as e:
        ctx.log.error(f"Failed to generate SQL: {e}")
        if hasattr(result, "set_error"):
            result.set_error(str(e))
            result.success = False
        else:
            result.error_message = str(e)
            result.success = False
        return

    if sql_result and sql_result.success:
        if output_file:
            ctx.log.info(
                f"SQL script written: {output_file} ({sql_result.statements_generated} statement(s))"
            )
        else:
            ctx.log.info(f"Generated {sql_result.statements_generated} statement(s):")
            ctx.log.info("")
            sql_script = getattr(sql_result, "sql_script", "") or ""
            _render_sql_script(ctx, sql_script)
    elif sql_result:
        ctx.log.error(f"Failed to generate SQL: {sql_result.error_message}")
        result.success = False


def _handle_diff(ctx: CliCommandContext) -> Tuple[bool, Any]:
    if not _validate_output_file_flag(ctx):
        return (False, None)

    (
        target_version,
        tags_list,
        exclude_tags_list,
        versions_list,
        exclude_versions_list,
    ) = _resolve_filter_lists(ctx)

    result = ctx.client.diff(
        snapshot_model=getattr(ctx.args, "snapshot_model", None),
        ignore_unmanaged=getattr(ctx.args, "ignore_unmanaged", False),
        target_version=target_version,
        tags=tags_list,
        exclude_tags=exclude_tags_list,
        versions=versions_list,
        exclude_versions=exclude_versions_list,
        recursive=ctx.recursive,
        additional_dirs=ctx.additional_scripts_dirs if ctx.additional_scripts_dirs else None,
    )

    if getattr(ctx.args, "generate_sql", False):
        _generate_and_render_sql(ctx, result)

    _set_command_completed(ctx.log, result, "DIFF")
    return (result.success, result)
