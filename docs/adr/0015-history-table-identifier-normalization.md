# 0015 — History-table identifier normalization

- Status: Accepted
- Date: 2026-04-20
- Deciders: Maintainers

## Context and problem statement

BUG-03 (dev-repo test skill): running ``repair`` against an Oracle
database fails with ``ORA-00942: table or view does not exist``. The
generated SQL is::

    DELETE FROM "DBLIFT_TEST"."dblift_schema_history"
    WHERE script = ? AND success = 0

Oracle folds unquoted identifiers to UPPERCASE at DDL time, so the
physical table is ``DBLIFT_SCHEMA_HISTORY``. Wrapping the lowercase
``dblift_schema_history`` in ANSI double-quotes tells Oracle "look
for a table literally named lowercase", which does not exist.

The ``migrate`` happy path does not trip the same bug because
``has_history_table`` already normalises the name via
``provider.get_normalized_object_name`` before probing — but that
normalisation was a one-off done inline in one property. Other call
sites that qualified the same identifier (``repair`` DELETE,
Flyway-compat check via ``provider.table_exists``) re-implemented the
pattern and forgot the normalisation step, producing the drift BUG-03
surfaced.

## Decision drivers

- Oracle / DB2: UPPERCASE; PostgreSQL / SQL Server / MySQL / SQLite /
  CosmosDB: lowercase. The correct case is already encoded in
  ``db/object_naming.py::get_normalized_object_name``.
- Every call site that feeds the history-table name into a qualified-
  name function (``get_schema_qualified_name``, ``table_exists``) must
  pass the normalised form. Forgetting is silent on lowercase-dialects
  and catastrophic on Oracle.
- The same structural fix we already applied for ADR-0012 and ADR-0013
  applies: make the correct-by-default path obvious, forbid the
  drift-prone raw path.

## Decision

Add ``MigrationHistoryManager.normalized_history_table`` as the single
source of truth. Every call site that qualifies the history-table
identifier routes through it. ``self.history_manager.history_table``
remains available for cases where the raw, operator-supplied name is
needed (debug logging, round-tripping to config), but any path that
builds SQL or probes existence MUST use the normalised property.

Three call sites were audited and rewired in this PR:

| Site | Bug fixed | New path |
|---|---|---|
| ``repair_command.py::_delete_failed_migration_entry`` | BUG-03 | ``get_schema_qualified_name(schema, normalized_history_table)`` |
| ``migration_validator.py::validate_flyway_compatibility`` × 2 probes | Latent Oracle drift on the Flyway-compat check | ``provider.table_exists(schema, normalized_history_table)`` |
| ``MigrationHistoryManager.has_history_table`` | Already correct | Rewired to use the new property for symmetry |

Sites that interpolate the history-table name unquoted into SQL
(validator.py:220 / 1353 both use ``{schema}.{history_table}`` without
quotes) are left unchanged: Oracle's own case-folding covers them.
They rely on the rule ``unquoted → database-default case``, which
works symmetrically on every dialect, so an operator-supplied mixed-
case name would still round-trip correctly at those call sites.

## Consequences

### Positive

- ``repair`` now works on Oracle — the most visible symptom.
- Flyway-compat detection on Oracle correctly sees the existing Dblift
  history table instead of falsely concluding it is absent.
- New code that needs to qualify the history-table name has an
  obvious correct-by-default entry point; the raw property stays but
  is documented as "debug/round-trip only" in its docstring.

### Negative

- One more property on ``MigrationHistoryManager``. Trivial surface.

### Neutral

- The unquoted-SQL call sites were not touched. They are correct
  today; promoting them to the normalised path for consistency would
  be an unnecessary churn.

## Follow-ups

None planned. The audit found three sites, all three fixed, and no
other code path qualifies the history-table identifier through a
quoting function.

## Links

- `core/migration/history/migration_history_manager.py` — property
- `core/migration/commands/repair_command.py` — BUG-03 call site
- `core/sql_validator/migration_validator.py` — Flyway-compat call
  sites
- `db/object_naming.py::get_normalized_object_name` — the dialect rule
  this ADR consistently threads through the history-table path
- ADR-0012 §Follow-ups — same structural pattern (single source of
  truth replacing drift-prone inline helpers)
- ADR-0013 — previous cluster shipped from the same dev-skill report
