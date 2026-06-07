# 0005 — stdout is machine-readable when `--format` is machine-readable

- Status: Accepted
- Date: 2026-04-19
- Deciders: Maintainers
- Supersedes: behaviour established in commit 217a5694

## Context and problem statement

Every dblift subcommand that offers a `--format` flag can produce output
in at least one format that downstream tooling is expected to parse:

| Subcommand | Machine-readable formats offered |
|---|---|
| `info` | `json` |
| `validate-sql` | `json`, `sarif`, `github-actions`, `gitlab`, `compact` |

For a machine-readable format, stdout is a **contract**: the caller
should be able to pipe stdout into `json.loads`, a SARIF parser, or a
GitHub Actions annotations consumer without stripping anything. Any
line prepended or appended by the process to stdout breaks that
contract.

Commit `217a5694` ("fix: banner suppression scoped to info command
only") intentionally narrowed the banner-suppression heuristic so that
only `info --format json` suppresses the startup banner. The narrowing
was in response to a Bugbot review comment on PR 158
(`discussion_r3106139669`) which read:

> The output_format check `getattr(args, "format", "table") != "json"`
> suppresses the human-readable banner whenever any command's
> `--format` is `"json"`. The `validate-sql` command also has a
> `--format` argument that accepts `"json"` (for SARIF/JSON lint
> output). Running `validate-sql --format json` incorrectly suppresses
> the main header banner.

The Phase 1 PR-01 stdout-contract test
(`test_validate_sql_json_stdout_has_no_trailing_banner`) failed after
this narrowing landed, with stdout containing:

```
================================================================================
DBLIFT DATABASE MIGRATION LOG
--------------------------------------------------------------------------------
Timestamp: ...
License: ...
================================================================================
{ "success": true, "violations": [ ... ] }
SQL validation completed successfully
```

Bugbot and the contract test are in direct conflict. Bugbot argued the
banner belongs on stdout because "it's human-readable context that the
user wants to see." The contract test argues the banner corrupts any
downstream parser.

## Decision drivers

- Downstream consumers (CI reporters, IDE integrations, shell pipes)
  reading `validate-sql --format json` must get parseable JSON. This is
  the whole point of offering `--format json`.
- The banner and license info are valuable to human users. They should
  not disappear entirely.
- A full redesign (banner on stderr, stdout on stdout) is a separate
  structural refactor tracked as Phase 2 PR-08
  ("`CommandOutput` abstraction"). It is out of scope for a functional
  regression gate.

## Considered options

1. **Suppress the banner on stdout whenever `--format` is
   machine-readable (current ADR).** Bug reported by Bugbot was a
   direction-of-fix disagreement, not a defect in the broader
   suppression. Restore the broader suppression and extend it to the
   full set of machine-readable formats validate-sql exposes.
2. Keep the banner only on `info --format json` (the post-217a5694
   state). Accept that `validate-sql --format json` emits non-JSON
   stdout. **Rejected** — this is the behaviour the contract test was
   introduced to block.
3. Re-architect the CLI output so banner and status go to stderr and
   only payload goes to stdout. **Right long-term, but Phase 2** (PR-08
   `CommandOutput`). Deferred.
4. Keep both banner and JSON on stdout, wrap them in a single JSON
   envelope. **Rejected** — breaks anyone reading the plain JSON shape
   (the violations array and success boolean).

## Decision outcome

Chosen option: **option 1**. Banner suppression on stdout applies to
any command whose `--format` value is in the set
`{"json", "sarif", "github-actions", "gitlab", "compact"}`. Additional
formats added in the future should be added to the same set.

This explicitly **supersedes the Bugbot thread's recommendation** on
commit `217a5694`. The decision is recorded here so the override is
traceable if the matter is revisited.

### Changes

- `cli/main.py`: replace the narrow `is_info_json` predicate with
  `is_machine_format`, tied to the shared set.
- `cli/_command_handlers.py::_handle_validate_sql`: skip the post-scan
  "SQL validation completed successfully" log line and
  `_set_command_completed` when `is_machine_format` (same pattern as
  the `info --format json` fix in `b72cc83a`). Also switch the
  formatter output to a direct `print()` in machine mode so the
  `ConsoleLog` formatter cannot prefix timestamps.
- `tests/integration/matrix/test_json_output_contract.py`:
  `test_validate_sql_json_stdout_is_parseable` and
  `test_validate_sql_json_stdout_has_no_trailing_banner` now pin the
  contract for validate-sql.

### Positive consequences

- `validate-sql --format json | jq .` and equivalent pipes work.
- The same contract holds for the other machine-readable formats the
  command already advertises (`sarif`, `github-actions`, `gitlab`).
- No silent banner contamination from any future command that opts
  into a machine-readable format, as long as it reuses the shared set.

### Negative consequences

- Human users running `validate-sql --format json` in a terminal lose
  the banner and license line. They can see both via `info --format
  table` or any non-machine-readable invocation. An auditor is
  unlikely to flag this as a regression; the contract justifies it.
- PR-08 (`CommandOutput` with stderr/stdout separation) supersedes this
  decision when it lands. The allowlist set becomes redundant once
  humans get banners on stderr unconditionally.

## Links

- Phase 1 PR-01: this change
- Phase 2 PR-08: `CommandOutput` abstraction (planned)
- Prior fix: commit `b72cc83a` (info --format json completion message)
- Prior fix: commit `217a5694` (scoped banner suppression)
- Bugbot thread: PR 158 review `discussion_r3106139669`
- `docs/stabilization-plan.md` — Phase 1
