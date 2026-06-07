# 0008 — `CommandOutput` abstraction for CLI routing

- Status: Accepted
- Date: 2026-04-19
- Deciders: Maintainers
- Supersedes: part of [0005](0005-stdout-machine-readability.md)

## Context and problem statement

The CLI has two classes of output:

1. **Machine payload** — JSON/SARIF/GitHub Actions annotations consumed
   by downstream tooling. Stdout is a *parser contract*; anything
   extra breaks it.
2. **Human status** — banner, license/database metadata, progress
   lines, completion summary. Expected on stdout when a human runs
   the command interactively.

ADR-0005 chose to **suppress** the banner in machine mode because
stdout had only one sink. That worked but discarded useful information
for humans who happen to run `dblift validate-sql --format json` in a
terminal: they lose the session context entirely.

The predicate `if output_format in MACHINE_READABLE_FORMATS` was also
duplicated across `cli/main.py` and `cli/_command_handlers.py` — the
exact pattern the stabilization plan (`docs/stabilization-plan.md` §
"Doubles sources de vérité") identifies as a root cause of bugs.
Bugbot on PR-06 flagged the inline set duplication; PR-01 addressed
that by extracting `MACHINE_READABLE_FORMATS` to `cli._constants`, but
the *routing logic* remained duplicated at every call site.

## Decision drivers

- Make the routing decision a single, named, testable object so call
  sites express intent (*"this is machine payload"*, *"this is human
  status"*) instead of re-deriving the format predicate.
- Preserve stdout as a pure parser contract in machine mode — PR-01
  contract tests still pass.
- Stop discarding banner/status information; route it to stderr
  instead so humans still see it.
- Keep human-format UX unchanged — no visible change for anyone
  running `dblift info` without `--format`.
- Stay small: no logger-level refactor, no breaking change to existing
  integrations that pipe `dblift <cmd>` > file.txt in human mode.

## Considered options

1. **Introduce `CommandOutput` with explicit `machine` / `status` /
   `banner` methods; route machine-mode status to stderr (this ADR).**
2. Route all logger output (INFO, DEBUG, WARN, ERROR) to stderr
   globally. Clean long-term, but breaks every user who currently
   redirects human stdout to a file.
3. Keep the PR-05 allowlist approach; accept the duplication. Leaves
   the pattern the stabilization program targets as a root cause.
4. Remove the banner entirely (always). Unacceptable regression in
   human mode.

## Decision outcome

Chosen option: **option 1**. The new module `cli/_output.py` defines:

```python
class CommandOutput:
    def machine(payload): ...   # stdout (JSON/SARIF/etc), no-op in human mode
    def status(message): ...    # stderr in machine mode, stdout in human mode
    def banner(text):   ...     # same routing as status
```

Plus a `from_args(args)` convenience constructor reading `args.format`.

### Call-site changes

- `cli/main.py`: the banner loop calls `command_output.banner(...)`
  instead of `print(header)` guarded by `is_machine_format`. The
  header now *always* prints — it just picks the right stream.
- `cli/_command_handlers.py::_handle_validate_sql`: the
  formatter-output print becomes `command_output.machine(output)`.
- `cli/_command_handlers.py::_handle_info`: the `json.dumps(...)`
  print becomes `command_output.machine(_info_result_to_dict(result))`.
- `MACHINE_READABLE_FORMATS` is no longer imported anywhere in
  `cli/_command_handlers.py` or `cli/main.py` — CommandOutput is the
  only consumer.

### Tests

`tests/unit/cli/test_output.py` — 23 tests covering:

- `is_machine_format` predicate for every format in
  `MACHINE_READABLE_FORMATS` plus human defaults;
- `machine()` behaviour for dict / list / pre-rendered string
  payloads, and no-op in human mode;
- `status()` / `banner()` stream routing in both modes;
- a stdout-purity test showing `status` calls do not contaminate the
  JSON stream;
- `from_args` convenience constructor edge cases.

Existing contract tests in
`tests/integration/matrix/test_json_output_contract.py` (PR-01) still
pass: stdout remains a pure JSON document after `--format json`.

### What changes for users

| Scenario | Before | After |
|---|---|---|
| `dblift info` (human) | stdout: banner + table | stdout: banner + table |
| `dblift info --format json` | stdout: JSON (banner suppressed) | stdout: JSON; **stderr: banner** |
| `dblift validate-sql --format json` | stdout: JSON | stdout: JSON; **stderr: banner** |
| `dblift info --format json > out.json` | out.json = JSON | out.json = JSON (banner visible to user in terminal) |
| `dblift info --format json 2>/dev/null` | out = JSON + no stderr | out = JSON + no stderr |

No breaking change for machine consumers; information gained for
humans.

### Positive consequences

- Duplicated `is_machine_format` computation eliminated from two
  modules; one import of `from cli._output import from_args` replaces
  a three-line predicate.
- `ADR-0005`'s allowlist stays as a dependency (the set lives in
  `cli._constants`), but the routing logic is now behind one
  interface.
- Opens the door to future refactors (ConsoleLog stderr routing,
  structured logging, progress reporting) without call-site churn.

### Negative consequences

- The banner is now *always* emitted on stderr in machine mode. If a
  user was relying on `dblift ... --format json` producing nothing on
  stderr (i.e. used `2>/dev/null` reflexively), they will see noise
  when they didn't before. This is information that *should* be
  available; the stdout contract is unaffected.

## Follow-ups

- ConsoleLog currently routes INFO/DEBUG to stdout. Full stderr
  routing is the natural next step; deferred because it requires
  coordinated changes across every test that greps stdout for log
  lines. Tracked for a future small PR.
- The linter rule `cli-print-stdout` in `scripts/lint_patterns.py`
  can narrow once all print() sites are migrated. The two remaining
  annotations (`--version` terminal action, multi-command separator)
  can be migrated to CommandOutput when the API grows.

## Links

- `cli/_output.py` — the abstraction
- `tests/unit/cli/test_output.py` — contract tests
- [ADR-0005](0005-stdout-machine-readability.md) — prior
  suppression-based decision (partially superseded)
- `docs/stabilization-plan.md` — Phase 2 PR-08
