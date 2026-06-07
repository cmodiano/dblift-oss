# 0007 — Dialect capabilities matrix

- Status: Accepted
- Date: 2026-04-19
- Deciders: Maintainers

## Context and problem statement

Dblift supports seven database dialects (PostgreSQL, Oracle, MySQL, SQL
Server, DB2, SQLite, Cosmos DB). Each dialect behaves differently along
several axes:

- transaction semantics (begin/commit/rollback, transactional DDL)
- schema model (schema-required vs schemaless)
- identifier case folding (uppercase for Oracle / DB2, lowercase
  elsewhere)
- clean strategy (native provider enumeration for file/document stores,
  metadata introspection walk for relational stores)

These differences are scattered across the code as:

- hand-typed dialect strings — `if dialect in ("sqlite", "cosmosdb"):`
  appears in at least eight files (comparators, commands, executor,
  export_schema).
- provider-instance predicates — `isinstance(self.provider,
  TransactionalProvider) and self.provider.supports_transactions()`
  appears in `execution_engine.py`, `repair_command.py`, and
  `migration_executor.py`.
- legacy frozensets — `SCHEMA_OPTIONAL_DIALECTS`, `NOSQL_DIALECTS`,
  `CASCADE_DROP_DIALECTS`, etc., introduced by SIMP-37 Phase 0 and now
  partially authoritative.

Bugbot flagged this family on PR 160: *"Snapshot skipped for SQLite
despite supporting transactions"* — the compound predicate produced a
false negative because `isinstance(…) AND supports_transactions()` is
over-restrictive. Related: *"SQLite schema missing from export-schema
skip check"*, where a tuple `("cosmosdb",)` did not include SQLite.

The shared root cause: there is no single authoritative declaration of
what a dialect supports, so every module re-derives the answer from a
mix of string checks and runtime introspection.

## Decision drivers

- Provide one place a reader can consult to know what any dialect
  supports.
- Encode the declaration as data so CI can assert provider runtime
  behaviour matches it (conformance test) rather than both being
  authoritative-by-convention.
- Preserve the SIMP-37 frozensets as derived views for backwards
  compatibility; no churn at existing call sites required.
- Keep the change small enough to ship as a single PR.

## Considered options

1. **Add a `DialectCapabilities` dataclass + `_CAPABILITIES` registry
   in `core/sql_model/dialect.py`, alongside the existing SIMP-37
   frozensets.** Provide named helpers (`dialect_supports_transactions`,
   `dialect_requires_schema`, etc.). Conformance tests assert the
   matrix matches provider behaviour. Existing call sites untouched.
2. Replace every scattered check at every call site in one PR.
   Correct but risky (touches 30+ sites; regression surface is big).
3. Make the providers authoritative (the runtime methods are the only
   truth). Remove string-based checks entirely. Reverse of what we
   want: scatters the question across provider classes instead of
   centralising it.
4. Do nothing — continue with scattered checks and hope the next bug
   is cheap to find.

## Decision outcome

Chosen option: **option 1**. It lands the architectural centre of
gravity in one file, enforces drift-prevention via tests, and keeps
the blast radius small (one new module section + one new test file).
Follow-up PRs can migrate individual call sites incrementally as the
refactor program matures.

### Matrix shape

```python
@dataclass(frozen=True)
class DialectCapabilities:
    supports_transactions: bool
    supports_transactional_ddl: bool
    schema_required: bool
    uppercase_identifiers: bool
    clean_strategy: str  # "native" | "jdbc"
```

The four boolean axes and the clean strategy capture every cross-
dialect decision the codebase currently makes outside of SQL grammar
(which stays in the parser). A future axis (e.g. supports
``CONCURRENT INDEX``) is added by extending the dataclass and every
entry; the type checker ensures no dialect is forgotten.

### Helpers

Named predicates for each axis (`dialect_supports_transactions`,
`dialect_supports_transactional_ddl`, `dialect_requires_schema`,
`dialect_uses_uppercase_identifiers`, `dialect_clean_strategy`) plus
`get_dialect_capabilities(dialect)` for callers that want the whole
record at once. All helpers:

- accept `Optional[str]` to match how dialect is plumbed today;
- fall back to a conservative "unknown" record (all `supports_*`
  false, `schema_required` true) rather than raising, so caller guards
  degrade safely;
- look up the matrix case-insensitively.

### Conformance

`tests/unit/core/sql_model/test_dialect_capabilities.py` asserts:

- every `DialectEnum` member (except `UNKNOWN`) has a matrix entry;
- the SIMP-37 `SCHEMA_OPTIONAL_DIALECTS` frozenset equals the
  matrix-derived subset — if someone changes one without the other,
  CI fails;
- provider runtime values for `supports_transactions()` and
  `supports_transactional_ddl()` match the matrix (CosmosDB / MySQL /
  Oracle are covered without needing a live database).

### Positive consequences

- A reader looking for "does dialect X support transactional DDL"
  consults one table. Today they grep three files.
- Provider-vs-matrix drift is caught by CI the next time the provider
  changes.
- The matrix doubles as a per-dialect capability contract that future
  PRs (e.g. PR-11 `CommandLifecycle`) can consume as input.

### Negative consequences

- The matrix is a second place to update when a dialect gains a new
  capability. The conformance test pins this to a hard failure in CI,
  so forgetting it cannot silently ship.
- Existing call sites still use the scattered checks. They are not
  buggy today (the conformance test proves matrix ≡ provider runtime),
  so we accept the deferred refactor.

## Follow-ups

- Call sites that do `isinstance(p, TransactionalProvider) and p.X()`
  can be migrated to the helper one file at a time, in future small
  PRs. No big-bang refactor is needed.
- PR-11 (`CommandLifecycle`) should consume the matrix to route
  transactional behaviour rather than ad-hoc isinstance checks.
- When a new dialect is added, the matrix is the first place to edit;
  the conformance test enumerates the missing entry.

## Links

- `core/sql_model/dialect.py` — matrix + helpers (PR-07)
- `tests/unit/core/sql_model/test_dialect_capabilities.py` — conformance tests
- SIMP-37 comment block in `core/sql_model/dialect.py` — prior work
  (frozensets already centralised)
- Bugbot thread PR 160 — "Snapshot skipped for SQLite despite
  supporting transactions"
- `docs/stabilization-plan.md` — Phase 2 PR-07
