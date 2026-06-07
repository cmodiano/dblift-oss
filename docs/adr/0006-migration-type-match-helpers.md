# 0006 — `MigrationType` matching helpers

- Status: Accepted
- Date: 2026-04-19
- Deciders: Maintainers

## Context and problem statement

Between v1.1.0 and v1.3.1 the project accumulated ~30 copies of the
same defensive comparison:

```python
migration_type == "SQL"
or str(migration_type) == "SQL"           # <-- dead for MigrationType enum
or (
    migration_type is not None
    and hasattr(migration_type, "name")
    and migration_type.name == "SQL"
)
```

Each site exists because callers cannot predict whether they receive a
`MigrationType` enum member (from in-memory migrations) or a plain
string (from persisted history table rows). Bugbot flagged the
middle branch as dead code on PR 160; other threads surfaced concrete
bugs where the middle branch was the *only* branch (e.g. `str(enum) in
VERSIONED_SCRIPT_TYPES`, which never matches for a real enum value
because `str(MigrationType.SQL) == "MigrationType.SQL"`, not `"SQL"`).

Three modules had already started solving the problem locally with
private helpers (`_get_migration_type_string`, `_is_migration_type_equal`)
— one copy each in:

- `core/migration/scripting/migration_script_manager.py`
- `core/migration/state/migration_state_service.py`
- `core/migration/ui/data_collector.py`

That is the exact "doubles (triples, here) sources of truth" pattern
documented as a root cause of the 44 % fix ratio in
`docs/stabilization-plan.md`. Any edit to one copy silently drifts
from the others.

PR-04 added an AST lint rule `enum-str-conversion` that detects new
occurrences of the pattern and freezes the 29 existing ones in a
baseline for mechanical cleanup.

## Decision drivers

- Eliminate the triple-defensive pattern at 29 call sites.
- Remove the three local helper duplicates.
- Keep a stable public contract so follow-up refactors (e.g. making
  `MigrationType` a `str`-subclass enum) can land without more churn.
- Preserve the exact current runtime behaviour — this refactor must
  not change what comparisons return, only how they are expressed.

## Considered options

1. **Add three helpers in a dedicated module
   (`core/migration/_type_match.py`)** and migrate all call sites to
   them. Keep the three local-module helpers as thin delegators for
   backwards compatibility.
2. Make `MigrationType` a `str`-subclass enum (`class MigrationType(str, Enum)`).
   Then `str(m) == "SQL"` works naturally. But this changes `str(enum)`
   semantics repo-wide and may affect serialisation.
3. Normalise at the boundary: every call that loads a history row
   converts the string into a `MigrationType`. Expensive and easy to
   miss; doesn't remove the triple-check elsewhere.
4. Do nothing — tolerate the 29 copies and the dead middle branch.

## Decision outcome

Chosen option: **option 1**. A new module
`core/migration/_type_match.py` exposes:

```python
def migration_type_name(value: Any) -> str
def is_versioned(value: Any) -> bool
def is_migration_type(value: Any, target: Union[MigrationType, str]) -> bool
```

All 29 lint-baseline occurrences were mechanically migrated. Of those:

- **8 were true MigrationType comparisons** (migration_rules,
  migration_analyzer, migration_data_service, migration.py __repr__/__str__,
  and the three local helper bodies). These now call the shared helpers.
- **21 were generic non-MigrationType `str(X_type)` patterns** (SQL
  statement types, DB column types, schema object types, command
  dispatch labels, constraint types, database dialect types). These are
  annotated with `# lint: allow-enum-str: <reason>` because the
  helpers are deliberately MigrationType-specific and using them here
  would be misleading.

The three local helper methods
(`_get_migration_type_string`, `_is_migration_type_equal`,
`_is_versioned_type`) remain on their classes but now delegate to the
shared helpers in a single line each. External callers are unaffected.

### Positive consequences

- `.lint-patterns-baseline.txt` shrinks from 29 entries to 0.
- Any new occurrence of the broken `str(migration_type)` pattern fails
  CI on first introduction (the lint rule stays in force).
- The canonical contract is encoded in 46 unit tests covering every
  input shape (enum member, string, `None`, duck-typed, non-string
  non-enum fallback).
- `is_migration_type(...)` reads like English at call sites; the
  triple-branch noise disappears.

### Negative consequences

- One more module to know about (`core/migration/_type_match.py`).
  Mitigated by the module docstring pointing to this ADR.
- Deferred imports in `core/migration/migration.py` (to avoid the
  `migration.py → _type_match → migration.py` cycle). Standard Python
  idiom; no runtime cost per call.

## Follow-ups

- Option 2 (`MigrationType` as `str`-subclass enum) is the natural
  long-term move. It subsumes this decision by making `str(enum) == "SQL"`
  true by construction. Tracked as a Phase 2 candidate; not required
  for stabilization.
- The `# lint: allow-enum-str` annotations on non-MigrationType enums
  could be removed if a sibling generic helper (`enum_value_or_name`)
  ships. Judgement call; left for a future PR if the pattern grows.

## Links

- PR-04 ADR scaffold and the lint rule `enum-str-conversion`
- `docs/stabilization-plan.md` — Phase 2 PR-06
- Bugbot threads on PR 160 — `get_reapplied_versions`,
  `determine_pending_migration_status`, `get_category_and_display_type`
  casing, `VERSIONED_SCRIPT_TYPES` enum lookups
- `tests/unit/core/migration/test_type_match.py` — contract tests
