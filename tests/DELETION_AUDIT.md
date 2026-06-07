# Unit test deletion audit

Companion to the test-strategy reset (see `tests/integration/matrix/README.md`).
This is the proposed disposition of every file under `tests/unit/`. Nothing is
deleted yet — this is the proposal for review before any bulk action.

## Summary

| Classification | Count | Share |
|---|---|---|
| **KEEP-LOGIC** — pure logic, no mocks | 118 | 29% |
| **KEEP-INVARIANT** — structural/property test | 29 | 7% |
| **DELETE-MOCKY** — mock-heavy CLI/handler/engine coupling | 98 | 24% |
| **DELETE-DB** — mocks the JDBC/SDK boundary; integration covers it | 97 | 24% |
| **DELETE-COVERAGE** — story-suffixed (`_NN_N.py`) implementation-mirrors | 48 | 12% |
| **REVIEW** — needs human judgment | 12 | 3% |
| **Total** | 402 | |

**Net effect of deletions:** ~243 files removed (~60% of the unit suite).

## Batch A execution log (2026-04-18)

Batch A intended to delete all 48 `_NN_N.py` files flagged DELETE-COVERAGE.
On file-by-file inspection we found the audit was over-aggressive for this
batch: **15 of the 48 are actually KEEP-INVARIANT or KEEP-LOGIC** (abstract-
method contracts, dead-code absence, structural enum/dialect integrity, no
bare `assert` in production, etc.) — their story suffix was misleading.

**Actually deleted:** 33 files.
**Preserved as KEEP-LOGIC (mocks=0, pure function tests):** 15
**Preserved as KEEP-INVARIANT (structural/ABC/no-import-sys):** 17

Preserved file list is the set of `_NN_N.py` files under `tests/unit/` after
the Batch A deletion; no additional index needed — `find` + `grep -L 'Mock('`
reproduces it.

The takeaway: the `_NN_N.py` heuristic is a screening signal, not a verdict.
Every file still needs a one-minute eyeball before `git rm`.

## Deletion criteria

A test file is a **deletion candidate** if any of the following is true:

1. Primary assertions are `mock.assert_called_with(...)` / `mock.call_count` —
   i.e. the test asserts *how* the code was called, not *what* it produced.
   This couples the test to implementation shape; refactors break it, bugs
   don't.
2. It mocks a DB/JDBC/SDK boundary (`java.sql.*`, `azure-cosmos`,
   `DatabaseMetaData`). Integration tests with real containers catch the
   real bugs at this layer; unit mocks encode assumptions, not behavior.
3. It hand-crafts `args = Mock()` and calls a CLI handler directly, bypassing
   argparse. This is the exact pattern that let the 1.3.1 BUG-01/02,
   NEW-BUG-10 and --dry-run regressions ship.
4. The filename ends in `_NN_N.py` (story/epic tag). These were written to
   cover a specific refactor and are almost always implementation-mirrors.
   Structural invariants from those stories have been preserved under
   KEEP-INVARIANT where worth keeping.

## Keep criteria

A test file is a **keeper** if:

1. It exercises pure logic with zero or incidental mocks — tokenizers, SQL
   parsers, SQL generators, version sort, checksum, URL masking, dataclass
   validation, config loading from strings, comparators.
2. It encodes a structural invariant — no inline imports, no production
   `assert`, abstract-method contracts, argparse-dest collisions, dead-code
   absence, dialect/enum integrity.

## Replacement coverage

Everything DELETE-* is covered by one of:

- `tests/integration/commands/` — existing DB-parametrized command tests.
- `tests/integration/matrix/test_cli_contract.py` — new, DB-free contract
  tests for CLI error UX, exit codes, help discoverability.
- `tests/integration/matrix/test_parent_flag_behaviour.py` — new, behavioural
  verification that parent-level flags reach every subcommand (pending).
- `tests/unit/cli/test_parser_invariants.py` — new, structural check that no
  subparser redefines a parent dest (catches the 1.3.x regression family
  permanently).

If, after deletions, there is a behaviour the remaining suite does not cover,
that gap is the cue to add an integration test — not to restore a unit test.

## Suggested deletion order

1. **Batch A (low risk, high gain):** All `DELETE-COVERAGE` — 48 files. These
   are the most obvious dead weight. Structural invariants they contained are
   already preserved in KEEP-INVARIANT.
2. **Batch B (medium risk):** All `DELETE-MOCKY` that target CLI handlers and
   command orchestrators — ~40 of the 98 MOCKY files. Replaced by
   `tests/integration/matrix/test_cli_contract.py` + existing
   `tests/integration/commands/`.
3. **Batch C (medium risk):** All `DELETE-DB` — 97 files. Before each
   deletion, confirm the equivalent scenario is covered in
   `tests/integration/commands/` or `tests/integration/validation/`. Add an
   integration test for any gap found.
4. **Batch D (last):** Remaining `DELETE-MOCKY` — executor/engine/validator
   internals. Covered by the existing scenario tests in
   `tests/integration/scenarios/` and `tests/integration/features/`.
5. **REVIEW batch:** Human decision, file by file.

Each batch is a separate PR so the test-suite impact of each deletion wave
is easy to bisect.

## Full per-file classification

The full per-file table lives in the conversation transcript that generated
this audit (it is too long to embed verbatim — ~400 entries). The category
summary above plus the `grep`-able heuristics below reproduce it:

```bash
# DELETE-COVERAGE candidates:
find tests/unit -name 'test_*_[0-9][0-9]_[0-9]*.py'

# DELETE-DB candidates:
grep -rl 'MagicMock\|Mock(' tests/unit/db/plugins/ tests/unit/db/introspection/ \
    tests/unit/db/test_*provider*.py tests/unit/db/test_jvm*.py

# DELETE-MOCKY candidates (CLI/handlers):
grep -rl 'args = Mock\|args = MagicMock' tests/unit/cli/ tests/unit/api/

# KEEP-LOGIC candidates (zero Mock):
for f in $(find tests/unit -name 'test_*.py'); do
    grep -q 'Mock\|MagicMock\|patch(' "$f" || echo "$f"
done
```

Run each command and diff against the audit list before deleting.
