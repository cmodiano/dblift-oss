# 0013 — OperationResult CLI reporting contract

- Status: Accepted
- Date: 2026-04-20
- Deciders: Maintainers

## Context and problem statement

Three bugs surfaced by the dev-repo test skill (BUG-01, BUG-02b, BUG-07)
share a root cause: the boundary between the command layer (which sets
`result.success` and `result.error_message`) and the CLI output layer
(which renders them) has no enforced contract. Each bug is a different
symptom of the same drift:

| Bug | Symptom |
|---|---|
| BUG-01 | `clean` without `--confirm` sets `result.error_message` (precise, actionable), but the command footer prints generic `"Command CLEAN failed (0 ms)"` and the message is never surfaced. |
| BUG-02b | `export-schema --managed-only` with zero matching objects writes a valid empty file successfully, then returns `False` because "0 items" is confused with "failure". CLI reports FAILED despite the file being correct on disk. |
| BUG-07 | `validate-sql` on PostgreSQL `$$`-quoted bodies throws a tokenizer error, which a broad `except` in `_validate_sql_syntax` catches. The file is counted as a pass, exit 0, "No issues found" — a green light over a real problem. |

Underneath these three symptoms: `OperationResult.success` is overloaded
(it conflates "I did the work" with "I produced non-empty output"), and
`error_message` is set by commands but not consulted by the footer
formatter, and broad `except` clauses deeper in the stack hide real
failures.

## Decision drivers

- Operators must always get an actionable explanation when a command
  fails. "Command X failed" without a reason is a regression by itself.
- "Empty but correct" is a valid successful outcome. Writing a valid
  empty export file is success; failing to connect is failure. These
  must not be reported the same way.
- Silent `except Exception` clauses in command paths are the exact
  anti-pattern already removed from `_plsql_block`, `_get_managed_objects`
  and `repair_command` during Phase Oracle and BUG-04/06 fixes. Same fix
  applies here.
- Each fix ships as its own PR with failing-test-first TDD, same cadence
  as ADR-0012 §Follow-ups.

## Decision

Three targeted PRs, each addressing one symptom but all honouring the
same pinned contract:

### PR-1 — Footer renders `error_message`

`BaseCommand._format_command_footer` takes a new optional
`error_message` parameter. When `success=False` and a message is set,
the footer includes an `Error: <message>` line between the status line
and the closing border. `_log_command_completion` passes
`result.error_message` through so every command that set one gets its
message rendered automatically — no per-command wiring. Multi-line
messages get indented under an `Error:` prefix so the footer block
stays visually distinct.

Tests: `tests/unit/core/migration/commands/test_command_footer_error_message.py`
pins four cases — error message present / absent, success path ignores
it, end-to-end propagation via `_log_command_completion`.

### PR-2 — "Empty-but-correct" returns success

`SchemaExporter._generate_and_write` with zero filtered objects writes
the empty-export file and currently returns `False`. Flip to `True` —
the file was written correctly, no errors occurred, there's nothing
more to do. The only information the empty case carries is a log line
about why the result was empty (already present, improved by the
BUG-02a diagnostic PR). The caller (`export_schema`) then reports
success and the CLI footer reflects that.

Tests: unit test driving `_generate_and_write` with an empty object
list asserts it returns `True`, the empty-export file exists, and no
error is set on the result.

### PR-3 — `validate-sql` surfaces tokenizer errors

`MigrationValidator._validate_sql_syntax` currently wraps its statement
split in `except Exception as split_error`, logs a warning, then calls
`validate_sql(script_content)` as a whole-file fallback. If the whole
file also fails to tokenize, the error is recorded. But if splitting
fails AND the whole-file validator also swallows (e.g. PostgreSQL
regex parser's tolerant path), the script is silently counted as
passing.

Fix: on split failure, explicitly mark the script as invalid in the
validation result (append to `issues`, set `success=False`,
populate `error_message`) — no silent fallback path. Let the legitimate
whole-file validator run, but if IT also can't parse the content, the
failure is recorded, not swallowed.

Tests: a unit test with a mocked `sql_analyzer` whose `split_statements`
raises asserts the validation result is marked failing and the error
message includes the tokenizer error.

## Consequences

### Positive

- Operators see actionable error messages on every failure.
- `--managed-only` with 0 results stops being noise ("FAILED" when the
  file is on disk and correct).
- `validate-sql` stops certifying syntactically-broken files as clean.
- Each PR stands alone — can be merged independently if one of the
  three needs revision.

### Negative

- PR-3 might unmask a small number of pre-existing tokenizer failures
  that were previously silent passes. These are real issues that
  should have been surfaced; the next skill run will tell us the
  count. Acceptable.

### Neutral

- The `OperationResult` dataclass itself doesn't change — the contract
  adjustment lives in the command-layer callers and the CLI-side
  renderer. No API break.

## Follow-ups

None planned. The three PRs complete the cluster. If future command
additions set `error_message` without surfacing it, the footer path
now renders it by default — new code inherits the fix.

## Links

- `core/migration/commands/base_command.py` — footer formatter
- `core/migration/commands/export_schema_command.py` — empty-export path
- `core/sql_validator/migration_validator.py` — validate-sql tokenizer path
- `docs/stabilization-plan.md` — BUG-01 / BUG-02b / BUG-07 tracking
- ADR-0012 — same split-fix-follow-ups cadence
