"""Private operation helpers for :mod:`api.client`.

Keep large operation bodies out of ``DBLiftClient`` so the public client class
stays readable while preserving the same public methods and behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from api.events import EventType
from core.logger.results import (
    ExportSchemaResult,
    GenerateSqlFromDiffResult,
    GenerateUndoScriptResult,
)
from core.migration.commands.export_schema_command import ExportSchemaOptions


def _heuristic_statement_count_from_sql(sql_text: str) -> int:
    """Count lines that look like standalone SQL statements (heuristic)."""
    return sum(
        1
        for line in sql_text.split("\n")
        if line.strip() and not line.strip().startswith("--") and line.strip().endswith(";")
    )


def _apply_sql_script_warning_scan(
    result: Union[GenerateSqlFromDiffResult, GenerateUndoScriptResult],
    sql_text: str,
) -> None:
    """Set manual-review flag and collect per-line warnings from generated SQL text."""
    sql_lower = sql_text.lower()
    if "warning" in sql_lower or "requires manual review" in sql_lower:
        result.requires_manual_review = True
        for line in sql_text.split("\n"):
            if "warning" in line.lower():
                warning_msg = line.strip().lstrip("--").strip()
                if warning_msg:
                    result.add_warning(warning_msg)


def _extract_schema_diff_input(
    diff: Optional[Any],
    diff_result: Optional[Any],
    result: GenerateSqlFromDiffResult,
) -> Optional[Any]:
    """Resolve the SchemaDiff input for ``generate_sql_from_diff_operation``.

    Returns the schema diff to operate on, or ``None`` if the input is missing
    or invalid (in which case the error is recorded on ``result`` and the
    result is marked complete — callers should return it as-is).
    """
    from core.comparison.diff_models import SchemaDiff

    schema_diff: Optional[Any] = None
    if diff is not None:
        schema_diff = diff
    elif diff_result is not None:
        if hasattr(diff_result, "schema_diff"):
            schema_diff = diff_result.schema_diff
        else:
            result.set_error("DiffResult does not contain a schema_diff")
            result.complete()
            return None

    if schema_diff is None:
        result.set_error(
            "No schema diff provided. Provide either 'diff' or 'diff_result' parameter."
        )
        result.complete()
        return None

    if not isinstance(schema_diff, SchemaDiff):
        result.set_error(
            f"'diff' must be a SchemaDiff instance, got {type(schema_diff).__name__}. "
            "To generate SQL from a snapshot, first produce a SchemaDiff via "
            "ObjectComparator.compare_schemas(expected, actual), or pass a DiffResult "
            "via diff_result=client.diff(...)."
        )
        result.complete()
        return None

    return schema_diff


def _build_sql_script_options(
    expected_objects: Optional[Dict[str, Any]],
    *,
    dialect: str,
    title: Optional[str],
    description: Optional[str],
    include_comments: bool,
    include_checks: bool,
) -> Any:
    """Construct ``GenerateSqlScriptOptions`` from a flat ``expected_objects`` dict."""
    from core.sql_generator.diff_to_sql import GenerateSqlScriptOptions

    def _expected(key: str) -> Any:
        return expected_objects.get(key) if expected_objects else None

    return GenerateSqlScriptOptions(
        expected_tables=_expected("tables"),
        expected_views=_expected("views"),
        expected_indexes=_expected("indexes"),
        expected_sequences=_expected("sequences"),
        expected_triggers=_expected("triggers"),
        expected_procedures=_expected("procedures"),
        expected_functions=_expected("functions"),
        expected_synonyms=_expected("synonyms"),
        expected_extensions=_expected("extensions"),
        expected_user_defined_types=_expected("user_defined_types"),
        expected_packages=_expected("packages"),
        expected_events=_expected("events"),
        expected_database_links=_expected("database_links"),
        expected_linked_servers=_expected("linked_servers"),
        expected_foreign_data_wrappers=_expected("foreign_data_wrappers"),
        expected_foreign_servers=_expected("foreign_servers"),
        dialect=dialect,
        title=title,
        description=description,
        include_comments=include_comments,
        include_checks=include_checks,
    )


def _build_diff_summary(schema_diff: Any) -> Dict[str, int]:
    """Project ``schema_diff`` to the four-counter summary dict surfaced on the result."""
    return {
        "total_differences": (
            schema_diff.get_total_diff_count()
            if hasattr(schema_diff, "get_total_diff_count")
            else 0
        ),
        "missing_tables": (
            len(schema_diff.missing_tables) if hasattr(schema_diff, "missing_tables") else 0
        ),
        "extra_tables": (
            len(schema_diff.extra_tables) if hasattr(schema_diff, "extra_tables") else 0
        ),
        "modified_tables": (
            len(schema_diff.modified_tables) if hasattr(schema_diff, "modified_tables") else 0
        ),
    }


def generate_sql_from_diff_operation(
    client: Any,
    *,
    diff: Optional[Any] = None,
    diff_result: Optional[Any] = None,
    output_file: Optional[Union[str, Path]] = None,
    expected_objects: Optional[Dict[str, Any]] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    include_comments: bool = True,
    include_checks: bool = True,
) -> GenerateSqlFromDiffResult:
    """Generate SQL from a diff for ``DBLiftClient.generate_sql_from_diff``."""
    from core.sql_generator.diff_to_sql import generate_sql_script

    result = GenerateSqlFromDiffResult()
    schema_diff = _extract_schema_diff_input(diff, diff_result, result)
    if schema_diff is None:
        return result

    dialect = client.dialect
    client.events.emit(
        EventType.MIGRATION_STARTED,
        {"operation": "generate_sql_from_diff", "dialect": dialect},
    )

    try:
        sql_options = _build_sql_script_options(
            expected_objects,
            dialect=dialect,
            title=title,
            description=description,
            include_comments=include_comments,
            include_checks=include_checks,
        )

        sql_script = generate_sql_script(diff=schema_diff, script_options=sql_options)
        result.statements_generated = _heuristic_statement_count_from_sql(sql_script)
        _apply_sql_script_warning_scan(result, sql_script)

        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(sql_script, encoding="utf-8")
            result.sql_file_path = str(output_path)

        result.diff_summary = _build_diff_summary(schema_diff)

        result.sql_script = sql_script
        result.success = True
        result.complete()
        client.events.emit(
            EventType.MIGRATION_COMPLETED,
            {"result": result, "operation": "generate_sql_from_diff"},
        )
        return result
    except Exception as e:
        error_msg = f"Failed to generate SQL from diff: {str(e)}"
        result.set_error(error_msg)
        result.complete()
        client.events.emit(
            EventType.MIGRATION_FAILED,
            {"error": error_msg, "operation": "generate_sql_from_diff"},
        )
        raise


def generate_undo_script_operation(
    client: Any,
    *,
    migration_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    overwrite: bool = False,
) -> GenerateUndoScriptResult:
    """Generate one undo script for ``DBLiftClient.generate_undo_script``."""
    result = GenerateUndoScriptResult()
    migration_path = Path(migration_path)
    result.migration_path = str(migration_path)
    if output_dir:
        output_dir = Path(output_dir)

    client.events.emit(
        EventType.MIGRATION_STARTED,
        {"operation": "generate_undo_script", "migration_path": str(migration_path)},
    )

    try:
        migration = _prepare_undo_generation_migration(client, migration_path)
        result = _generate_undo_script_for_migration(
            client,
            migration_path=migration_path,
            migration=migration,
            output_dir=output_dir,
            overwrite=overwrite,
        )
        client.events.emit(
            EventType.MIGRATION_COMPLETED,
            {"result": result, "operation": "generate_undo_script"},
        )
        return result
    except FileNotFoundError as e:
        _emit_undo_generation_failure(client, result, str(e))
        raise
    except (FileExistsError, ValueError) as e:
        _emit_undo_generation_failure(client, result, str(e))
        return result
    except Exception as e:
        _emit_undo_generation_failure(client, result, f"Failed to generate undo script: {str(e)}")
        raise


def generate_undo_scripts_operation(
    client: Any,
    *,
    migration_paths: Optional[List[Union[str, Path]]] = None,
    migrations_dir: Optional[Union[str, Path]] = None,
    overwrite: bool = False,
    recursive: bool = True,
    **kwargs: Any,
) -> List[GenerateUndoScriptResult]:
    """Generate many undo scripts for ``DBLiftClient.generate_undo_scripts``."""
    results: List[GenerateUndoScriptResult] = []

    if migration_paths is None:
        migrations_dir = (
            client._get_scripts_dir() if migrations_dir is None else Path(migrations_dir)
        )
        pattern = "**/V*.sql" if recursive else "V*.sql"
        migration_paths = [f for f in migrations_dir.glob(pattern) if f.is_file()]
    else:
        migration_paths = [Path(p) for p in migration_paths]

    client.events.emit(
        EventType.MIGRATION_STARTED,
        {"operation": "generate_undo_scripts", "count": len(migration_paths)},
    )

    for migration_path in migration_paths:
        try:
            migration_path_typed = (
                Path(migration_path) if isinstance(migration_path, str) else migration_path
            )
            client.events.emit(
                EventType.MIGRATION_STARTED,
                {
                    "operation": "generate_undo_script",
                    "migration_path": str(migration_path_typed),
                },
            )
            migration = _prepare_undo_generation_migration(client, migration_path_typed)
            result = _generate_undo_script_for_migration(
                client,
                migration_path=migration_path_typed,
                migration=migration,
                output_dir=kwargs.get("output_dir"),
                overwrite=overwrite,
            )
            client.events.emit(
                EventType.MIGRATION_COMPLETED,
                {"result": result, "operation": "generate_undo_script"},
            )
            results.append(result)
        except (FileNotFoundError, FileExistsError, ValueError) as e:
            error_result = _undo_script_error_result(migration_path, str(e))
            results.append(error_result)
            client.events.emit(
                EventType.MIGRATION_FAILED,
                {"error": str(e), "operation": "generate_undo_script"},
            )
        except Exception as e:
            error_msg = f"Failed to generate undo script: {str(e)}"
            results.append(_undo_script_error_result(migration_path, error_msg))
            client.events.emit(
                EventType.MIGRATION_FAILED,
                {"error": error_msg, "operation": "generate_undo_script"},
            )

    client.events.emit(
        EventType.MIGRATION_COMPLETED,
        {
            "operation": "generate_undo_scripts",
            "results": results,
            "success_count": sum(1 for r in results if r.success),
            "failure_count": sum(1 for r in results if not r.success),
        },
    )
    return results


def _prepare_undo_generation_migration(client: Any, migration_path: Path) -> Any:
    """Validate a path once and return the parsed SQL versioned migration.

    Returns a ``core.migration.migration.Migration`` — typed as ``Any``
    here to avoid a top-level import cycle (``Migration`` transitively
    pulls in ``api`` via the executor).
    """
    from core.migration.formats import MigrationFormat
    from core.migration.migration import Migration
    from core.migration.scripting.migration_script_manager import MigrationScriptManager

    if not migration_path.exists():
        raise FileNotFoundError(f"Migration file not found: {migration_path}")

    script_manager = MigrationScriptManager(client.logger)
    if not script_manager.is_versioned_script_name(migration_path.name):
        raise ValueError(
            f"File is not a versioned migration: {migration_path.name}. "
            "Expected a versioned migration filename (V*__description.<ext>)."
        )

    migration = Migration(script_path=migration_path, logger=client.logger)
    if not migration.version:
        raise ValueError(f"Could not extract version from: {migration_path.name}")
    if migration.format != MigrationFormat.SQL:
        raise ValueError(
            "Automatic undo script generation supports SQL migrations (V*__.sql) only. "
            f"{migration_path.name} uses format {migration.format.value}; add a hand-written "
            "U*__.sql undo script instead."
        )
    return migration


def _generate_undo_script_for_migration(
    client: Any,
    *,
    migration_path: Path,
    migration: Any,
    output_dir: Optional[Union[str, Path]],
    overwrite: bool,
) -> GenerateUndoScriptResult:
    """Generate an undo script for an already validated Migration."""
    from core.migration.scripting.undo_script_generator import UndoScriptGenerator

    result = GenerateUndoScriptResult()

    output_dir_path: Optional[Path] = None
    if output_dir and output_dir != "":
        output_dir_path = Path(output_dir) if isinstance(output_dir, str) else output_dir
    if output_dir_path is None:
        output_dir_path = migration_path.parent

    generator = UndoScriptGenerator(dialect=client.dialect, logger=client.logger)
    expected_undo_path = generator.get_undo_script_path_for_migration(
        migration,
        output_dir=output_dir_path,
    )
    file_existed_before = expected_undo_path.exists()
    # Use the pre-parsed-migration entry point so the file isn't re-parsed
    # (we already validated + constructed ``migration`` in
    # ``_prepare_undo_generation_migration``). Bugbot review on PR #382.
    undo_path = generator.generate_undo_script_for_migration(
        migration,
        output_dir=output_dir_path,
        overwrite=overwrite,
    )

    if undo_path.exists():
        content = undo_path.read_text()
        result.statements_generated = _heuristic_statement_count_from_sql(content)
        _apply_sql_script_warning_scan(result, content)

    if overwrite and file_existed_before:
        result.overwritten = True

    result.migration_path = str(migration_path)
    result.undo_script_path = str(undo_path)
    result.success = True
    result.complete()
    return result


def _emit_undo_generation_failure(
    client: Any, result: GenerateUndoScriptResult, error_msg: str
) -> None:
    result.set_error(error_msg)
    result.complete()
    client.events.emit(
        EventType.MIGRATION_FAILED,
        {"error": error_msg, "operation": "generate_undo_script"},
    )


def _undo_script_error_result(
    migration_path: Union[str, Path], error_message: str
) -> GenerateUndoScriptResult:
    result = GenerateUndoScriptResult()
    result.migration_path = str(migration_path)
    result.set_error(error_message)
    result.complete()
    return result


def _build_export_schema_options(
    client: Any,
    output: Optional[Union[str, Path]],
    output_dir: Optional[Union[str, Path]],
    split_by_type: bool,
    tables: Optional[Union[str, List[str]]],
    types: Optional[Union[str, List[str]]],
    unmanaged_only: bool,
    managed_only: bool,
    include_drops: bool,
    schema: Optional[str],
    description: Optional[str],
    source: str,
    snapshot_model: Optional[Union[str, Path]],
    tags: Optional[str],
    exclude_tags: Optional[str],
    versions: Optional[str],
    exclude_versions: Optional[str],
    target_version: Optional[str],
) -> ExportSchemaOptions:
    """Assemble an ``ExportSchemaOptions`` from the kwargs passed to ``DBLiftClient.export_schema``.

    Encapsulates the per-kwarg → options-dataclass translation so the public
    method body stays focused on dispatching.
    """
    tables_str = ",".join(tables) if isinstance(tables, list) else tables
    types_str = ",".join(types) if isinstance(types, list) else types

    scripts_dir = client._get_scripts_dir()
    additional_dirs = getattr(client.config.migrations, "directories", [])

    return ExportSchemaOptions(
        output=str(output) if output else None,
        output_dir=str(output_dir) if output_dir else None,
        split_by_type=split_by_type,
        tables=tables_str,
        types=types_str,
        unmanaged_only=unmanaged_only,
        managed_only=managed_only,
        include_drops=include_drops,
        schema=schema,
        description=description,
        scripts_dir=scripts_dir,
        additional_scripts_dirs=([Path(d) for d in additional_dirs] if additional_dirs else None),
        recursive=getattr(client.config.migrations, "recursive", True),
        tags=tags,
        exclude_tags=exclude_tags,
        versions=versions,
        exclude_versions=exclude_versions,
        target_version=target_version,
        source=source,
        snapshot_model=str(snapshot_model) if snapshot_model else None,
    )


def export_schema_operation(
    client: Any,
    *,
    output: Optional[Union[str, Path]] = None,
    output_dir: Optional[Union[str, Path]] = None,
    split_by_type: bool = False,
    tables: Optional[Union[str, List[str]]] = None,
    types: Optional[Union[str, List[str]]] = None,
    unmanaged_only: bool = False,
    managed_only: bool = False,
    include_drops: bool = False,
    schema: Optional[str] = None,
    description: Optional[str] = None,
    source: str = "live-database",
    snapshot_model: Optional[Union[str, Path]] = None,
    tags: Optional[str] = None,
    exclude_tags: Optional[str] = None,
    versions: Optional[str] = None,
    exclude_versions: Optional[str] = None,
    target_version: Optional[str] = None,
    options: Optional[ExportSchemaOptions] = None,
) -> ExportSchemaResult:
    """Implementation of ``DBLiftClient.export_schema``.

    When ``options`` is provided it takes precedence; the individual kwargs
    are then ignored (consistent with the prior in-method behavior).
    """
    from core.migration.commands.export_schema_command import export_schema as export_schema_impl

    if options is not None:
        if not isinstance(options, ExportSchemaOptions):
            raise TypeError(
                "options must be an ExportSchemaOptions instance, got " f"{type(options).__name__}"
            )
        opts = options
    else:
        opts = _build_export_schema_options(
            client,
            output=output,
            output_dir=output_dir,
            split_by_type=split_by_type,
            tables=tables,
            types=types,
            unmanaged_only=unmanaged_only,
            managed_only=managed_only,
            include_drops=include_drops,
            schema=schema,
            description=description,
            source=source,
            snapshot_model=snapshot_model,
            tags=tags,
            exclude_tags=exclude_tags,
            versions=versions,
            exclude_versions=exclude_versions,
            target_version=target_version,
        )

    # Event emission contract matches the other operations in this module
    # (see ``generate_sql_from_diff_operation`` / ``generate_undo_script_operation``):
    # EXPORT_STARTED before the work, EXPORT_COMPLETED on success,
    # EXPORT_FAILED on exception or soft failure. Exceptions are re-raised
    # after emission so callers still observe the failure. Payload keys are
    # restricted to the
    # ``Event`` dataclass's declared fields — ``_build_event`` rejects
    # unknowns with ``TypeError``, so emit-site fields like ``source``,
    # ``split_by_type``, or ``success`` would crash the emit before the
    # export even begins. Use ``operation`` / ``result`` / ``error`` —
    # the same set the sibling generate_* operations emit.
    client.events.emit(
        EventType.EXPORT_STARTED,
        {"operation": "export_schema"},
    )

    try:
        success = export_schema_impl(
            config=client.config,
            options=opts,
            executor=client.executor,
            log=client.logger,
            provider=getattr(client, "provider", None),
        )
    except Exception as exc:
        client.events.emit(
            EventType.EXPORT_FAILED,
            {"error": str(exc), "operation": "export_schema"},
        )
        raise

    # Build the full ``ExportSchemaResult`` BEFORE the COMPLETED emit so
    # listeners receive the same shape sibling operations send: a
    # completed result object (with ``.success``, ``.execution_time()``,
    # …) rather than the raw boolean returned by ``export_schema_impl``.
    result = ExportSchemaResult(success=success)
    result.complete()

    if result.success:
        client.events.emit(
            EventType.EXPORT_COMPLETED,
            {"result": result, "operation": "export_schema"},
        )
    else:
        client.events.emit(
            EventType.EXPORT_FAILED,
            {"result": result, "operation": "export_schema"},
        )

    return result
