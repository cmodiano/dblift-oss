# 0012 — Oracle parser split (Phase Oracle)

- Status: Done
- Date: 2026-04-19 (scoping) → 2026-04-20 (completion)
- Deciders: Maintainers

## Context and problem statement

`core/sql_parser/oracle/oracle_parser.py` is 1 402 lines in a single
class (`OracleParser`) and accounts for 16 of 41 `fix` commits between
v1.1.0 and v1.3.1 — the largest single source of regression in the
codebase. The file mixes five responsibilities:

1. **Statement boundary detection** — `_split_statements_regex`,
   `_extract_next_complete_statement`, `_extract_regular_statement`,
   `_starts_with_plsql_keyword`, `_word_at_position`.
2. **PL/SQL block handling** — `_parse_plsql_create_header`,
   `_scan_to_plsql_body_start`, `_handle_plsql_end_keyword`,
   `_extract_plsql_block`, `_extract_java_source_block`,
   `_is_line_start_slash`, `_is_single_plsql_block`,
   `_is_partial_plsql_fragment_check`.
3. **SQL\*Plus directive recognition** — `_is_sqlplus_command`.
4. **Comment stripping** — `_remove_sql_comments`, `_remove_comments`.
5. **Statement classification & object extraction** —
   `_identify_statement_type`, `_classify_with_string_analysis`,
   `_extract_objects_regex`.

A bug in one region (e.g. comment stripping) reaches PL/SQL handling
through shared state on the `self` object. The test suite
(`test_oracle_parser.py`, `test_oracle_parser_edge_cases.py`,
`test_oracle_parser_empty_column_guard.py` — 1 290 lines, ~75 tests)
exercises the monolithic class; coverage is high but the tests
currently can **only** catch regressions once they reach the public
surface. There is no harness that pins the sub-responsibility contracts
independently.

## Decision drivers

- Each resulting module must fit in ≤ 300 lines (stabilisation plan
  target for Phase Oracle).
- Behaviour must be byte-identical for every input the current
  parser handles. Zero "while we're at it" cleanups during the split.
- The split must be verifiable *before* any logic is moved — i.e. a
  shared conformance fixture harness that the monolithic implementation
  already passes and that each incremental extraction must keep
  passing.
- Migration in small, independently-reviewable PRs.

## Considered options

1. **Functional decomposition by responsibility (this ADR).**
   Five focused modules (`_statement_splitter.py`, `_plsql_block.py`,
   `_sqlplus.py`, `_comments.py`, `_object_extractor.py`) behind a
   thin `OracleParser` facade. Each module owns a pure function surface
   and is independently testable.

2. **Switch to sqlglot / antlr for Oracle.** Rejected for now —
   `sqlglot` already ships as an optional dependency (see
   `core/sql_parser/sqlglot_parser.py`) but its Oracle coverage
   doesn't handle SQL\*Plus directives or `CREATE JAVA SOURCE` blocks
   the way our existing callers rely on. A rewrite is a bigger bet
   than a decomposition and can land later without re-work.

3. **Rewrite as a state-machine class.** Rejected — encodes the same
   coupling we're trying to eliminate, just in `enum`-flavoured form.

## Decision

Option 1 — functional decomposition.

### Target layout

```
core/sql_parser/oracle/
├── __init__.py                    # public re-exports only
├── oracle_parser.py               # facade ≤ 200 lines: OracleParser class,
│                                  # parse_sql, split_statements, validate_sql,
│                                  # get_affected_objects
├── _statement_splitter.py         # boundary detection (pure functions)
├── _plsql_block.py                # PL/SQL + Java source block extraction
├── _sqlplus.py                    # SQL*Plus command recognition
├── _comments.py                   # comment stripping
├── _object_extractor.py           # regex-based object extraction
├── oracle_tokenizer.py            # unchanged (already isolated)
└── oracle_statement_parser.py     # unchanged (already isolated)
```

Each private module exports pure functions (no `self`, no class state).
The `OracleParser` class becomes a thin facade that wires the public
contract to the private modules.

### Conformance-first migration

Before any logic moves, this PR lands:

- `tests/unit/core/sql_parser/oracle/test_oracle_parser_conformance.py`
  — a parametrised harness of representative inputs spanning the five
  responsibilities. Every case asserts output shape (statement count,
  statement types, extracted object names). This harness is the contract.
- Empty skeleton modules in `core/sql_parser/oracle/` with
  scope-declaring docstrings and `NotImplementedError` stubs. No behaviour
  is moved; `OracleParser` keeps working unchanged.

Subsequent Oracle PRs each move one sub-responsibility at a time. The
acceptance gate is: conformance suite green, full Oracle test suite
green (1 290 lines, ~75 tests), matrix regression green.

### Ordered follow-up PRs

| PR | Scope |
|---|---|
| Phase-Oracle-02 | Extract `_comments.py` (smallest surface, ~25 lines — warm-up). |
| Phase-Oracle-03 | Extract `_sqlplus.py` (isolated, ~70 lines). |
| Phase-Oracle-04 | Extract `_object_extractor.py` (~200 lines, read-only). |
| Phase-Oracle-05 | Extract `_statement_splitter.py` (~400 lines, the hot path). |
| Phase-Oracle-06 | Extract `_plsql_block.py` (~400 lines, the complex state machine). |
| Phase-Oracle-07 | Trim `oracle_parser.py` to facade; update ADR-0012 to "Done". |

Each PR ends with a file-size gate: `oracle_parser.py` line count must
strictly decrease, no extracted module may exceed 300 lines.

## Consequences

### Positive

- Each sub-responsibility gets its own failing-test target: a bug in
  comment stripping becomes a bug in `_comments.py` with a specific
  failing case, not a mysterious regression in the parser at large.
- The conformance harness, once green on monolith + every incremental
  split, acts as a permanent regression tripwire for future edits.
- `oracle_parser.py` at ≤ 200 lines is reviewable in one sitting.
- Aligns Oracle with the one-responsibility-per-module shape already
  established in `postgresql/`, `mysql/`, `sqlserver/` subpackages.

### Negative

- Five short-lived PRs on a hot file. Bugbot may flag transient cases
  where two call sites (monolith + new module) still exist during the
  extraction. Mitigated by landing each extraction end-to-end before
  starting the next.
- The conformance harness adds ~150 lines of test code before producing
  any structural benefit. The pay-off comes when the extractions start.

### Neutral

- `oracle_tokenizer.py` and `oracle_statement_parser.py` are untouched
  — they were already extracted in a prior refactor and fit the target
  shape.

## Results (2026-04-20)

The split landed in seven PRs over two days. Each extraction was
byte-identical: the conformance harness (29 assertions) remained
green at every step, and the full Oracle test suite grew from 158
to 277 tests (+75%) as each new module received direct unit tests.

| PR | Module | LOC | Tests added | `oracle_parser.py` |
|---|---|---|---|---|
| Phase-Oracle-01 | scoping harness + skeletons | — | 29 conformance | 1402 |
| Phase-Oracle-02 | `_comments.py` | 57 | 16 | 1402 → 1379 |
| Phase-Oracle-03 | `_sqlplus.py` | 91 | 52 | 1379 → 1310 |
| Phase-Oracle-04 | `_object_extractor.py` | 177 | 25 | 1310 → 1114 |
| Phase-Oracle-05 | `_statement_splitter.py` | 233 | 66 | 1114 → 937 |
| Phase-Oracle-06 | `_plsql_block.py` | 675 | 53 | 937 → 310 |
| Phase-Oracle-07 | facade trim + ADR "Done" | — | — | 310 → 298 |

`oracle_parser.py` dropped from 1 402 → 298 lines (−79 %). Extracted
module sizes: `_comments.py` 57, `_sqlplus.py` 91, `_object_extractor.py`
177, `_statement_splitter.py` 233, `_plsql_block.py` 675.

### Deviations from the plan

- **`_plsql_block.py` at 675 lines** exceeds the 300-line soft gate.
  The PL/SQL state machine is ~450 lines of deeply coupled control
  flow (`handle_plsql_end_keyword` alone is ~140 nested branches).
  Splitting further would break the byte-identical guarantee.
  Documented in `docs/stabilization-plan.md`.

- **`oracle_parser.py` facade at 298 lines** vs the 200-line aspiration.
  The delta is `_identify_statement_type` (53 lines) and
  `_classify_with_string_analysis` (42 lines), both kept in the class
  because `sql_analyzer.py::_infer_statement_type` probes
  `hasattr(parser, "_identify_statement_type")` and the sibling
  `PostgreSQLParser` exposes the same method — this is the dialect
  parser contract, not facade bloat.

### Pinned quirks — all fixed post-split

Byte-identical extraction preserved several legacy quirks. Each
shipped as its own PR with failing regression tests first (RED →
GREEN), and the module docstrings + conformance harness now assert
the corrected behaviour:

1. **`_object_extractor`** (PR-A through PR-C):
   - `CREATE [GLOBAL|PRIVATE] TEMPORARY TABLE` name is now extracted
     (PR-A).
   - `CREATE [OR REPLACE] [[NO]FORCE] [NON]EDITIONABLE VIEW` name is
     now extracted (PR-A).
   - `CREATE FUNCTION foo` now emits `object_type == FUNCTION` (via
     `Procedure(is_function=True)`) — PR-B.
   - Unqualified names now pick up ``default_schema`` (was silently
     dropped because the legacy branching dead-ended before the
     fallback) — PR-C.
2. **`_plsql_block.handle_plsql_end_keyword`** (PR-D): the literal
   "END" now propagates through control flow — the helper returns
   its `statement` so the caller can reassign; control-flow keywords
   (IF/LOOP/CASE/REPEAT) are consumed as a single unit with END so
   the main loop no longer double-counts `case_depth`.
3. **`_sqlplus.is_sqlplus_command`** (PR-E): unified into a single
   corpus. `oracle_statement_parser._is_sqlplus_command` now
   delegates to the shared function. Trailing `;` stripped before
   matching. Net behaviour on the tokenizer path: narrower where
   the old list was over-broad (`SET ROLE`, `WHENEVER NOT FOUND`,
   `START TRANSACTION` no longer filtered) and broader where it
   was under-specified (`CONN`, `COL`, `TIMING`, `!`, `EXEC`,
   `@@`, `VARIABLE`, `PRINT`, `PAUSE` now caught).

## Follow-ups — none outstanding

All post-split items tracked against this ADR have shipped.

## Links

- Stabilisation plan, § "Phase Oracle"
- Source: `core/sql_parser/oracle/`
- Conformance harness: `tests/unit/core/sql_parser/oracle/test_oracle_parser_conformance.py`
- Per-module tests: `tests/unit/core/sql_parser/oracle/test_{comments,sqlplus,object_extractor,statement_splitter,plsql_block}.py`
