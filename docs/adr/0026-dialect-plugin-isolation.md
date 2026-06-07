# 0026 — Dialect plugin isolation (DialectQuirks boundary)

- Status: Accepted
- Date: 2026-05-03
- Deciders: Maintainers
- Supersedes: extends ADR 0007 (Dialect capabilities matrix)

## Context and problem statement

Adding a new database backend to dblift today requires editing ~15 files
across `core/`, `api/`, `cli/`, and `config/`. The 2026-05-03 audit
counted **829 hardcoded dialect-name string literals outside `db/`**
(`grep` of `"postgresql" / "oracle" / "mysql" / …` excluding tests):

- `core/sql_generator/sql_generator.py` — 20 `dialect.lower() == "X"`
  branches.
- `core/sql_generator/{postgresql,mysql,oracle,sqlserver,db2,sqlite}_generator.py`
  + `alter/{X}_alter_generator.py` × 7 — dialect-named files inside the
  framework.
- `core/sql_parser/{X}/` × 7 + `core/sql_parser/dialects/{X}_config.py` × 6
  — same pattern for parsers.
- `core/sql_model/dialect.py` — 38 dialect string occurrences.
- `core/comparison/`, `core/sql_validator/`, `core/normalization/` —
  dozens more.

This produced compound-predicate bugs (PR 160 Bugbot: "Snapshot skipped
for SQLite despite supporting transactions") because every site
re-derives capability rules independently.

ADR 0007 introduced `DialectCapabilities` (data: booleans, enums) but
left **behaviour** (rendering, parsing, comparator quirks, type maps)
scattered across `core/`. This ADR closes the gap.

## Decision

Adopt a single behaviour-overlay protocol: **`DialectQuirks`**.

- Declared in `core/dialect_boundary.py` as the aggregate of six
  per-concern sub-protocols (`DdlQuirks`, `ParserQuirks`, `ModelQuirks`,
  `ComparatorQuirks`, `ValidatorQuirks`, `TypeMapQuirks`).
- Default implementation in `db/base_quirks.py` (`BaseQuirks`).
- Per-plugin override in `db/plugins/<X>/quirks.py`. Subclass overrides
  only the hooks whose behaviour differs from the default.
- Resolved through `ProviderRegistry.get_quirks(db_type)` and exposed
  on every provider as `provider.quirks`.

Framework code becomes branch-free: `if dialect == "oracle"` becomes
`provider.quirks.<hook>(...)`. Plugins are the single source of truth
for everything dialect-specific.

The protocol surface is empty in story 26-2 (this commit). Subsequent
stories (26-3..26-11) move framework branches into hooks one subsystem
at a time. Story 26-14 closes the epic when the lint baseline hits 0.

## Decision drivers

1. **Plug-and-play target.** Adding a dialect = drop one self-contained
   `db/plugins/<X>/` package + 1 entry-point line. Zero edits to
   `core/`, `api/`, `cli/`, or `config/`.
2. **Bug class elimination.** PR 160-style compound-predicate bugs
   disappear when capability checks live in one declaration that the
   framework consults consistently.
3. **Third-party ecosystem.** `provider.quirks` + entry-point discovery
   (story 26-12) lets a `dblift-snowflake` package ship without
   forking core.
4. **Incremental rollout.** Each story merges independently; hooks are
   added per subsystem; the 829-entry lint baseline ratchets down
   each merge.

## Considered options

1. **Status quo + ADR 0007 only.** Capabilities-as-data covers ~10 % of
   the leak. The remaining 90 % is rendering and parsing logic that
   `DialectCapabilities` cannot express. Rejected.

2. **One god-class `DialectAdapter` with all hooks on it.** Considered.
   Rejected because it concentrates change in one file and conflates
   unrelated concerns (DDL rendering vs lint rules vs type maps).
   Sub-protocols give each story a clean review surface and let
   plugins implement only what they need.

3. **Replace `DialectCapabilities` (ADR 0007).** Tempting but
   unnecessary. Capabilities (data) and quirks (behaviour) compose
   cleanly: capabilities answer "can?"; quirks answer "how?". Both
   stay.

4. **Decompose by class hierarchy alone (deeper inheritance).**
   Already partially done via the ISP-decomposed
   `provider_interfaces.py`. Inheritance scales poorly across the
   diff/parser/comparator axes — composition through `DialectQuirks`
   is the correct level of indirection for these concerns.

## Architectural shape

```
core/dialect_boundary.py
    DialectQuirks (Protocol, runtime_checkable)
        ├── DdlQuirks         # filled by 26-3
        ├── ParserQuirks      # filled by 26-4
        ├── ModelQuirks       # filled by 26-5
        ├── ComparatorQuirks  # filled by 26-6
        ├── ValidatorQuirks   # filled by 26-7
        └── TypeMapQuirks     # filled by 26-8

db/base_quirks.py
    BaseQuirks  # safe defaults; satisfies DialectQuirks

db/plugins/<X>/quirks.py
    <X>Quirks(BaseQuirks)  # overrides only the deltas

db/provider_registry.py
    PluginInfo.quirks_class: Optional[Type[BaseQuirks]] = None
    ProviderRegistry.get_quirks(db_type) -> BaseQuirks

db/base_provider.py
    BaseProvider.quirks  # cached property → ProviderRegistry.get_quirks(...)
```

## Consequences

### Positive
- Single hook catalogue. `core/dialect_boundary.py` is the master
  directory.
- Adding a hook = adding it to one Protocol + one default in
  `BaseQuirks`. Removing a `if dialect == "X"` branch = updating one
  call site.
- Lint guard (story 26-1) freezes regression: the 829-entry baseline
  shrinks each story.
- Third-party plugins indistinguishable from first-party (with story
  26-12 entry-points).

### Negative
- Indirection cost: `provider.quirks.<hook>()` instead of an inline
  branch. Resolved-once-cached property keeps it negligible.
- Migration churn: 11 stories (26-3..26-13) over ~7 weeks. Mitigated
  by the per-subsystem story shape — nothing big-bang, every PR small.
- Ergonomics: domain models (`core/sql_model/*`) lose dialect-aware
  rendering and become pure data. Story 26-5 owns this trade.

## Implementation plan

See `docs/architecture/EPIC-26-dialect-plugin-isolation.md` for the
14-story breakdown and 7-week schedule.

## Verification

- Conformance test: `tests/unit/db/test_dialect_quirks_conformance.py`.
- Lint guard: `scripts/lint_patterns.py` rule `dialect-string-literal`,
  baseline `.lint-patterns-baseline.txt`.
- Definition of done (epic-level): zero `dialect-string-literal`
  baseline entries; new dialect (MariaDB, story 26-13) shipped without
  any edit to `core/`, `api/`, `cli/`, or `config/`.

## References

- Epic plan: `docs/architecture/EPIC-26-dialect-plugin-isolation.md`
- ADR 0007 — Dialect capabilities matrix
- ADR 0012 — Oracle parser split (precedent for dialect-specific
  extraction)
