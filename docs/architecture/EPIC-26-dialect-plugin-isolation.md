# Epic 26 — Dialect plugin isolation

> **Goal**: Adding a new database dialect = drop one self-contained package under `db/plugins/<name>/` and register one entry-point. Zero edits to `core/`, `api/`, `cli/`, or `config/`. No `if dialect == "x"` branches anywhere outside the plugin.

- **Branch**: `epic/dialect-plugin-isolation` (off `main` @ 4d2281c6)
- **Worktree**: `.claude/worktrees/dialect-plugin-isolation`
- **Status**: Drafting (2026-05-03)
- **Predecessor**: ADR 0007 (Dialect capabilities matrix) — partial; this epic completes it.

---

## 1. Context

### Current state (audit 2026-05-03)

Adding a dialect today requires editing ~15 files across `core/`. Hard data:

| Symptom | Evidence |
|---|---|
| Dialect-named files in `core/` | `core/sql_generator/{postgresql,mysql,oracle,sqlserver,db2,sqlite}_generator.py` (~100 KB total), `core/sql_generator/cosmosdb_sdk_translator.py` (61 KB), `core/sql_generator/alter/{X}_alter_generator.py` × 7, `core/sql_parser/{X}/` × 7, `core/sql_parser/dialects/{X}_config.py` × 6 |
| Hardcoded `dialect.lower() == "x"` switches | `core/sql_generator/sql_generator.py` = 20 branches; `core/validation/round_trip_tester.py` = 18; `core/sql_model/dialect.py` = 38 string occurrences |
| Total non-test files mentioning a dialect outside `db/` | 105 files |
| `db/` files mentioning *another* dialect | 55 (own-dialect refs ok; cross-dialect refs not) |
| Domain models doing dialect checks | `core/sql_model/{base,sequence,procedure,index,trigger,event,synonym,package}.py` |
| Comparator quirks | `core/comparison/{comparator,sequence_comparator,index_comparator,type_normalizer,comparison_utils}.py` (≥38 hits) |
| Validator quirks | `core/sql_validator/migration_validator.py`, `core/sql_validator/linting/{sql_linter,performance_analyzer}.py` |
| Normalization tables | `core/normalization/{type_mappings,type_mapper,identifier_normalizer}.py` |
| CLI dispatch | `cli/_command_handlers.py` (11 hits — mostly skip-flags, error messages) |

### Why this matters

1. **No plug-and-play.** A third party cannot ship `dblift-snowflake` as a separate Python package — they must fork `core/`.
2. **Combinatorial bug surface.** Bugbot PR 160 (cited in ADR 0007): "Snapshot skipped for SQLite despite supporting transactions" — compound predicate `isinstance(...) AND supports_transactions()` was over-restrictive because each site re-derives capability rules independently.
3. **Onboarding tax.** Adding MariaDB or Cockroach means tracing every dialect string through ~100 files.
4. **Bloat.** Per-dialect surface ≈ 5 KLoC; Flyway's per-dialect jars carry ≈ 8–42 classes. We are paying ~30–50× the per-dialect maintenance cost for a feature set that should compress that ratio.

### What ADR 0007 already gave us

ADR 0007 introduced `DialectCapabilities` dataclass + `_CAPABILITIES` registry in `core/sql_model/dialect.py` for a small set of axes (transactions, schema-required, identifier case, clean strategy). It made progress on **runtime predicates** but did not address **code generation, parsing, type mapping, or comparator quirks** — the bulk of the leak. This epic builds on ADR 0007's pattern and extends it across all subsystems.

---

## 2. Target architecture

### End-state plugin shape

```
db/plugins/<dialect>/
├── __init__.py            # exports plugin metadata
├── plugin.py              # PluginInfo + capabilities + factory wiring
├── provider.py            # ConnectionProvider / TransactionalProvider impl
├── connection_manager.py
├── query_executor.py
├── schema_operations.py
├── locking_manager.py
├── history_manager.py
├── parser/                # was: core/sql_parser/<dialect>/
│   ├── tokenizer.py
│   ├── statement_parser.py
│   ├── regex_parser.py
│   └── parser_config.py   # was: core/sql_parser/dialects/<dialect>_config.py
├── generator/             # was: core/sql_generator/<dialect>_generator.py
│   ├── ddl_generator.py
│   └── alter_generator.py # was: core/sql_generator/alter/<dialect>_alter_generator.py
├── type_map.py            # was: dialect-specific rows in core/normalization/type_mappings.py
├── quirks.py              # implements DialectQuirks protocol — single home for "X is special"
├── capabilities.py        # DialectCapabilities instance (extends ADR 0007 matrix)
└── tests/                 # plugin-local tests
```

### `core/` boundary contract

`core/` exposes **interfaces only**. New file: `core/dialect_boundary.py` is the master directory of every hook a plugin can implement. Adding a hook = ADR + edit one file. Calling a hook = `provider.quirks.<hook>(...)`.

```python
# core/dialect_boundary.py (sketch)

class DialectQuirks(Protocol):
    """Single-source contract for dialect-specific behaviour."""

    # --- Code generation ---
    def render_sequence_default(self, seq: Sequence) -> str: ...
    def render_check_constraint(self, c: CheckConstraint) -> str: ...
    def render_event_trigger(self, e: Event) -> str: ...
    def needs_schema_qualifier(self) -> bool: ...
    def quote_identifier(self, ident: str) -> str: ...
    def supports_transactional_ddl(self) -> bool: ...

    # --- Comparison ---
    def normalize_type(self, raw: str) -> str: ...
    def compare_sequence(self, left: Sequence, right: Sequence) -> Diff: ...
    def compare_index(self, left: Index, right: Index) -> Diff: ...

    # --- Parsing ---
    def parser_factory(self) -> Parser: ...
    def parser_config(self) -> ParserConfig: ...

    # --- Validation ---
    def lint_rules(self) -> Iterable[LintRule]: ...
    def perf_rules(self) -> Iterable[PerfRule]: ...

    # --- Type mapping ---
    def type_map(self) -> Mapping[str, CanonicalType]: ...

    # --- Clean / drop ---
    def droppable_object_types(self) -> Sequence[ObjectType]: ...
    def cascade_drop(self) -> bool: ...
```

Concrete plugin extends `BaseQuirks` (defaults) and overrides only what differs.

### Plugin discovery

```toml
# pyproject.toml
[project.entry-points."dblift.providers"]
postgresql = "db.plugins.postgresql.plugin:plugin"
mysql      = "db.plugins.mysql.plugin:plugin"
oracle     = "db.plugins.oracle.plugin:plugin"
sqlserver  = "db.plugins.sqlserver.plugin:plugin"
db2        = "db.plugins.db2.plugin:plugin"
sqlite     = "db.plugins.sqlite.plugin:plugin"
cosmosdb   = "db.plugins.cosmosdb.plugin:plugin"
```

`ProviderRegistry` discovers via `importlib.metadata.entry_points("dblift.providers")` — first-party + third-party packages indistinguishable. Removes the in-process import-time registration at `db/provider_registry.py`.

### Anti-regression guard

Extend `scripts/lint_patterns.py` with rule `dialect-string-literal`:
- **Forbidden**: dialect-name string literals (`"postgresql"`, `"oracle"`, …) in `core/`, `api/`, `cli/`, `config/`.
- **Allowed**: `db/plugins/<X>/**` mentioning own dialect; `db/base_provider.py`, `db/provider_registry.py`; test files; sites annotated `# lint: allow-dialect-string: <reason>`.
- Baseline existing 105 sites in `.lint-patterns-baseline.txt`. Each story shrinks the baseline.

CI fails on any *new* violation. Existing violations tracked as TODO with a story ID.

---

## 3. Inventory of leak sites — "Hit list"

Grouped by leverage (tackle fattest first).

| Group | Files | Strings + branches | Story |
|---|---|---|---|
| **A — Generators** | `core/sql_generator/{postgresql,mysql,oracle,sqlserver,db2,sqlite,cosmosdb_sdk_translator}_generator.py` + `alter/{X}_alter_generator.py` × 7 + `generator_factory.py` + `alter_generator_factory.py` | ~7 dialect modules ≈ 105 KB; sql_generator.py central hub = 20 branches | 26-3 |
| **B — Parsers** | `core/sql_parser/{postgresql,mysql,oracle,sqlserver,db2,sqlite,cosmosdb}/` + `dialects/{X}_config.py` + `parser_factory.py` + `hybrid_parser.py` | 7 packages + 6 config files; parser_factory.py = 15 hits | 26-4 |
| **C — Domain models** | `core/sql_model/{dialect,base,sequence,procedure,index,trigger,event,synonym,package,view,table,extension,foreign_data_wrapper,foreign_server,user_defined_type,database_link,linked_server,module,constraint_validator}.py` | 38 + 14 + 12 + 9 + … (≥85 hits) | 26-5 |
| **D — Comparison** | `core/comparison/{comparator,sequence_comparator,index_comparator,type_normalizer,comparison_utils}.py` | ≥38 hits | 26-6 |
| **E — Validation** | `core/sql_validator/migration_validator.py`, `linting/{sql_linter,performance_analyzer}.py` | ~25 hits | 26-7 |
| **F — Normalization / type mapping** | `core/normalization/{type_mappings,type_mapper,identifier_normalizer}.py` | 12 + 6 + 12 hits | 26-8 |
| **G — Migration engine** | `core/migration/executor/execution_engine.py`, `core/migration/scripting/undo_script_generator*` | 14 + 11 + 6 + 6 hits | 26-9 |
| **H — CLI / commands** | `cli/_command_handlers.py`, `core/migration/commands/export_schema_command.py`, `core/sql_generator/safety_checker.py` | 11 + 9 + 17 hits | 26-10 |
| **I — Config** | `config/database_config.py`, `config/dblift_config.py`, `core/constants.py` | 35 + 23 + 8 hits | 26-11 |

---

## 4. Migration strategy — incremental, no big-bang

### Principles

1. **One subsystem per story.** Generators first, then parsers, then comparators, etc. Each story merges to `epic/dialect-plugin-isolation` without breaking the build.
2. **Boundary first, internals second.** Define the hook in `core/dialect_boundary.py` + `BaseQuirks` default impl + plugin override **before** removing the central `if dialect == X` site. Both coexist briefly; the central site delegates to `provider.quirks.<hook>()`. Then dead branches deleted.
3. **Lint baseline shrinks each story.** Every PR runs `python scripts/lint_patterns.py --write-baseline` and commits the diff. Reviewer checks shrinkage.
4. **Conformance test per hook.** For every hook in `DialectQuirks`, a test loops every registered plugin and asserts non-default override or explicit "default-ok" annotation. Regression on coverage = test fails.
5. **Move, don't rewrite.** First pass moves files into plugin folders behind the new hook. Second pass (post-epic) simplifies. Resist refactoring inside the move.

### Per-story workflow

```
1. Define new hook(s) in core/dialect_boundary.py + BaseQuirks default
2. Implement hook in each db/plugins/<X>/quirks.py (move existing code)
3. Wire central call site to provider.quirks.<hook>()
4. Delete old `if dialect == X` branches at the call site
5. Update lint baseline (it shrinks)
6. Run full test suite — must remain green
7. PR review — reviewer verifies baseline shrunk + no new dialect strings in core/
```

---

## 5. Stories

### 26-1 — Lint guard for dialect string leaks (quick win, no functional change)

**Why first.** Stops the bleeding. Every subsequent story shrinks the baseline. Without this, every fix risks a regression on adjacent code.

**Tasks**:
1. Add `dialect-string-literal` rule to `scripts/lint_patterns.py`. AST-based: detect `Constant(value=str)` matching `{"postgresql","postgres","oracle","mysql","mariadb","sqlserver","db2","sqlite","cosmosdb"}` outside allowlist (`db/plugins/<X>/**`, `db/base_provider.py`, `db/provider_registry.py`, `tests/**`, `scripts/**`, `docs/**`).
2. Generate baseline: ~105 violations recorded in `.lint-patterns-baseline.txt`.
3. Wire into `.github/workflows/code-quality.yml`.
4. Add `# lint: allow-dialect-string: <reason>` escape hatch.

**Acceptance**:
- CI fails on adding new dialect string in `core/`/`api/`/`cli/`/`config/`.
- Baseline file lists every existing site with `:dialect-string-literal` rule.
- README of rule explains migration path.

**Effort**: 0.5 day.

---

### 26-2 — Hook catalogue + `DialectQuirks` protocol + `BaseQuirks` defaults

**Tasks**:
1. Create `core/dialect_boundary.py` with `DialectQuirks` Protocol covering every category in the inventory.
2. Create `db/base_quirks.py` with `BaseQuirks` providing safe defaults (raise `NotImplementedError` only for hooks that have no sensible default; otherwise return value matching most-common dialect).
3. Each existing plugin gets `db/plugins/<X>/quirks.py` extending `BaseQuirks` with one stub method per hook; bodies still raise `NotImplementedError("filled by 26-3")` so type-checks pass without behaviour change.
4. Wire `provider.quirks` accessor on `BaseProvider`.
5. ADR 26 — record decision (supersedes/extends ADR 0007).

**Acceptance**:
- `from core.dialect_boundary import DialectQuirks` importable.
- `provider.quirks` returns a `DialectQuirks` instance for every dialect.
- No behaviour change yet — pure scaffolding.
- Conformance test: every plugin's `quirks` is an instance of `DialectQuirks`.

**Effort**: 1 day.

---

### 26-3 — Move generators into plugins

**Scope**: Group A from inventory.

**Tasks**:
1. For each dialect, move `core/sql_generator/<X>_generator.py` → `db/plugins/<X>/generator/ddl_generator.py`; same for `alter/<X>_alter_generator.py` → `db/plugins/<X>/generator/alter_generator.py`.
2. `core/sql_generator/generator_factory.py` and `alter_generator_factory.py` query `provider.quirks.ddl_generator()` / `provider.quirks.alter_generator()` instead of importing dialect modules.
3. `core/sql_generator/sql_generator.py` 20 branches → `provider.quirks.render_*()` calls. Keep the 20 hooks listed in `DialectQuirks` (to be added in 26-2).
4. `core/sql_generator/cosmosdb_sdk_translator.py` (61 KB) → `db/plugins/cosmosdb/cosmos_sdk_translator.py`.

**Acceptance**:
- `core/sql_generator/` contains no file named after a dialect.
- `core/sql_generator/sql_generator.py` has zero `dialect.lower() == ...` branches.
- Lint baseline drops by ≥30 entries.
- All migrate / diff / generate tests green.

**Effort**: 1 week.

---

### 26-4 — Move parsers into plugins

**Scope**: Group B.

**Tasks**:
1. Move `core/sql_parser/<X>/` → `db/plugins/<X>/parser/`.
2. Move `core/sql_parser/dialects/<X>_config.py` → `db/plugins/<X>/parser/parser_config.py`.
3. `core/sql_parser/parser_factory.py` becomes a thin façade: `provider.quirks.parser_factory()`.
4. `core/sql_parser/hybrid_parser.py` 8 hits → quirks (`provider.quirks.supports_sqlglot()`, `provider.quirks.statement_parser()`).
5. Keep `core/sql_parser/{base_*, common, parser_interface}.py` — these are the framework.

**Acceptance**:
- `core/sql_parser/` only contains framework files (`base_*`, `common/`, `parser_interface.py`, `parser_context.py`, `tokens.py`).
- Lint baseline drops by ≥25.
- Parser tests green per dialect.

**Effort**: 1 week.

---

### 26-5 — Domain models stop branching on dialect

**Scope**: Group C.

**Pattern**: `core/sql_model/sequence.py`'s `if dialect_lower == "oracle": ...` becomes `provider.quirks.render_sequence_default(self)`. Domain object stays dialect-agnostic; rendering is owned by the dialect.

**Tasks**:
1. Audit each `core/sql_model/*.py` for dialect branches.
2. For each branch, add a hook in `DialectQuirks` (only if not already present from 26-3).
3. Move logic into `db/plugins/<X>/quirks.py`.
4. Domain model calls `provider.quirks.<hook>(self)`. **Note**: domain models must accept a quirks/provider param OR the rendering moves entirely out of the model into the generator. Prefer the latter — domain models should be pure data.

**Acceptance**:
- `core/sql_model/dialect.py` becomes a registry only — no `if key == "oracle"` branches; all logic delegated.
- `grep -rn "dialect" core/sql_model/` shows only type annotations and registry keys.
- Lint baseline drops by ≥85.

**Effort**: 1 week.

---

### 26-6 — Comparator hooks

**Scope**: Group D.

**Tasks**:
1. `core/comparison/comparator.py`'s 7 dialect refs → `provider.quirks.compare_<object>()`.
2. `core/comparison/type_normalizer.py` (11 hits) → `provider.quirks.normalize_type(raw)`.
3. `core/comparison/sequence_comparator.py`, `index_comparator.py` similar.
4. `core/comparison/comparison_utils.py` 7 hits → utility functions take `quirks` parameter.

**Acceptance**:
- `core/comparison/` has zero dialect string literals.
- Diff/snapshot integration tests green per dialect.
- Lint baseline drops by ≥38.

**Effort**: 4 days.

---

### 26-7 — Validator hooks

**Scope**: Group E.

**Tasks**:
1. `core/sql_validator/migration_validator.py` Oracle-specific paths → `provider.quirks.lint_rules()`.
2. `core/sql_validator/linting/sql_linter.py` (15 hits) → quirks-driven rule set.
3. `core/sql_validator/linting/performance_analyzer.py` (7 hits) → `provider.quirks.perf_rules()`.

**Acceptance**:
- `validate-sql` SARIF output unchanged across all dialects.
- Lint baseline drops by ≥25.

**Effort**: 3 days.

---

### 26-8 — Type mapping owned by plugin

**Scope**: Group F.

**Tasks**:
1. `core/normalization/type_mappings.py` (12 hits) splits: each dialect's row table moves to `db/plugins/<X>/type_map.py`.
2. `core/normalization/type_mapper.py` queries `provider.quirks.type_map()`.
3. `core/normalization/identifier_normalizer.py` (12 hits) → `provider.quirks.quote_identifier()` / `provider.quirks.fold_case()`.

**Acceptance**:
- `core/normalization/` retains framework only (canonical type registry, normalizer interface).
- Lint baseline drops by ≥30.

**Effort**: 3 days.

---

### 26-9 — Migration engine + undo script generator

**Scope**: Group G.

**Tasks**:
1. `core/migration/executor/execution_engine.py` (14 hits) — most are transactional / autocommit checks, already reachable via `TransactionalProvider` + ADR 0007 capabilities. Replace with capability checks.
2. `core/migration/scripting/undo_script_generator*` (≥23 hits across 3 files) → `provider.quirks.render_undo_*()`.

**Acceptance**:
- Migrate command unchanged from user PoV.
- Lint baseline drops by ≥25.

**Effort**: 3 days.

---

### 26-10 — CLI / commands cleanup

**Scope**: Group H.

**Tasks**:
1. `cli/_command_handlers.py` 11 hits — these are mostly skip-flags and error messages. Replace skip-checks with capability queries (`provider.capabilities.supports_X`).
2. `core/migration/commands/export_schema_command.py` 9 hits — same.
3. `core/sql_generator/safety_checker.py` 17 hits — this file is per-dialect-safety-rule; either move into plugins (one rule set per `db/plugins/<X>/safety_rules.py`) or expose as `provider.quirks.safety_rules()`.

**Acceptance**:
- `cli/` has zero dialect string literals.
- Lint baseline drops by ≥40.

**Effort**: 3 days.

---

### 26-11 — Config + constants final pass

**Scope**: Group I.

**Tasks**:
1. `config/database_config.py` (35 hits) — many are dialect-specific config field validation. Each plugin owns its config sub-schema; framework composes.
2. `config/dblift_config.py` (23 hits) — same pattern.
3. `core/constants.py` (8 hits) — likely dialect lists; replace with `ProviderRegistry.list_dialects()`.

**Acceptance**:
- `config/` and `core/constants.py` have zero dialect string literals.
- Lint baseline drops by ≥60.

**Effort**: 3 days.

---

### 26-12 — Plugin discovery via entry points

**Tasks**:
1. Add `[project.entry-points."dblift.providers"]` block to `pyproject.toml`.
2. Rewrite `db/provider_registry.py` to read entry points via `importlib.metadata`.
3. Each plugin gets `db/plugins/<X>/plugin.py` exporting a `plugin: PluginInfo` symbol.
4. Document third-party plugin recipe in `docs/architecture/database-providers.md`.
5. End-to-end test: package a fake `dblift-fakedb` plugin in tests, install it, assert dblift discovers it.

**Acceptance**:
- `db/provider_registry.py` no longer hardcodes any dialect.
- Third-party plugin install works in test.
- Lint baseline drops by ≥10.

**Effort**: 1 day.

---

### 26-13 — Add MariaDB plugin (proof of plug-and-play)

**Why**: Validates the architecture. MariaDB ≈ MySQL + 2–3 quirks. If adding MariaDB requires only a new plugin folder + entry-point, the epic succeeded.

**Tasks**:
1. Create `db/plugins/mariadb/` extending MySQL plugin classes where possible.
2. Override quirks: MariaDB-specific `SHOW CREATE TABLE` differences, sequence support, JSON type.
3. Add `mariadb = "..."` to `pyproject.toml` entry points.
4. Add a tier-0 functional test (connect, migrate, info, diff).

**Acceptance**:
- Zero edits to `core/`, `api/`, `cli/`, `config/`.
- All MariaDB tests green.
- Closes the gap with Flyway OSS coverage.

**Effort**: 2 days.

---

### 26-14 — Lint baseline empty + close epic

**Tasks**:
1. Verify `.lint-patterns-baseline.txt` has zero `dialect-string-literal` entries.
2. Update ADR 0007 status to Superseded by ADR 26.
3. `docs/architecture/database-providers.md` rewritten as the authoritative plug-and-play recipe.
4. Add `docs/development/adding-a-dialect.md` — step-by-step guide using MariaDB (26-13) as worked example.

**Acceptance**:
- A new contributor can read `adding-a-dialect.md` and ship a new plugin without touching `core/`.
- Lint enforces the contract going forward.

**Effort**: 1 day.

---

## 6. Risk register

| Risk | Mitigation |
|---|---|
| **Big-bang refactor breaks a release.** | Each story merges independently to `epic/dialect-plugin-isolation`; CI green per story; epic merges to `develop` only after 26-14. Optionally squash-merge per group (A–I) into `develop` if epic stays open too long. |
| **Hook proliferation — `DialectQuirks` becomes a god interface.** | Group hooks into sub-protocols (`DdlQuirks`, `ParserQuirks`, `ComparatorQuirks`, `ValidatorQuirks`); `DialectQuirks` composes them. Each plugin's `quirks.py` mixes only what it needs. |
| **Performance regression** from extra indirection. | Quirks resolved once at provider construction; method calls are direct. Bench `migrate` + `diff` on PostgreSQL before/after; gate on no regression. |
| **Tests duplicate existing dialect coverage in plugin folders.** | Move-not-copy. Each story moves test files alongside the code they cover. |
| **Domain model purity vs ergonomics** (story 26-5). | Decision: domain models become pure data. All rendering lives in generators. If a model exposes `__str__` / `__repr__` doing dialect-specific rendering today, replace with `Generator.render(model)` calls. |
| **Third-party plugins shipping broken capability declarations.** | Conformance test (26-2) runs in `dblift verify-plugin <name>` CLI; recommended in plugin author docs. |

---

## 7. Definition of done (epic-level)

| Criterion | Check |
|---|---|
| `grep -rn 'dialect.lower()\s*==' core/ api/ cli/ config/` returns zero | CI |
| Dialect string literals in `core/`/`api/`/`cli/`/`config/` = 0 | `scripts/lint_patterns.py` |
| Files in `core/` named after a dialect = 0 | `find core -name "*postgresql*" -o -name ...` returns empty |
| New dialect (MariaDB, 26-13) shipped without `core/` edits | git diff |
| `docs/development/adding-a-dialect.md` exists | manual |
| All existing functional tests green per dialect | CI matrix |
| ADR 26 written and accepted | docs/adr/0026-*.md |

---

## 8. Sequencing & estimate

| Wave | Stories | Cumulative effort |
|---|---|---|
| **Foundation** (week 1) | 26-1, 26-2 | 1.5 days |
| **Code generation** (weeks 2–3) | 26-3, 26-4 | +2 weeks |
| **Domain & semantics** (weeks 4–5) | 26-5, 26-6, 26-7, 26-8 | +2.5 weeks |
| **Engine, CLI, config** (week 6) | 26-9, 26-10, 26-11 | +1.5 weeks |
| **Discovery + proof** (week 7) | 26-12, 26-13, 26-14 | +0.5 week |

**Total**: ~7 calendar weeks single-stream. Stories 26-3..26-8 partly parallelisable across two contributors.

---

## 9. Open questions (to resolve before story 26-2)

1. **Where do quirks instances live?** On the provider directly (`provider.quirks`) or as a sibling fetched by registry (`registry.quirks(dialect)`)? Lean towards `provider.quirks` for locality; revisit if circular import emerges.
2. **Capabilities vs Quirks split.** ADR 0007's `DialectCapabilities` is data (booleans, enums). `DialectQuirks` is behaviour (callables). Keep both — capabilities answer "can?", quirks answer "how?".
3. **Backwards compatibility for `import core.sql_generator.postgresql_generator`?** Plugins are first-party; no external code should import these paths. Drop in one go (no shim layer). If we later need shims, do them as a separate story.
4. **Plugin packaging** — first-party plugins ship inside the dblift wheel under `db/plugins/<X>/`; pluggable via the same entry-point mechanism that third parties use. No two registration paths.
5. **CosmosDB SDK translator (61 KB)** — does it stay one file or split? Move-not-rewrite for this epic; defer split to a follow-up.

---

## 10. References

- ADR 0007 — Dialect capabilities matrix
- ADR 0012 — Oracle parser split (precedent for dialect-specific extraction)
- ADR 0015 — History table identifier normalization (precedent for capability-driven dispatch)
- Comparison report: `~/.claude/plans/users-cyrille-documents-flyway-core-12-luminous-sprout.md`
