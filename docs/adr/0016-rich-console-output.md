# 0016 — Rich-based console output

- Status: Accepted
- Date: 2026-04-27
- Deciders: Maintainers

## Context and problem statement

dblift produces four output sinks per command run:

1. **Console** (stderr) — human-facing log lines.
2. **Text log file** — replay of the run for archival.
3. **JSON log file** — machine-parseable events.
4. **HTML log file** — rich report for sharing.

Until this change, console output was assembled by `TextFormatter` and
written via `print(..., file=sys.stderr)`. Tables used `prettytable`,
diff hierarchies used hand-built ASCII (`+----+`, `| col |`),
command footers used `"=" * 80`, tracebacks were raw
`traceback.print_exc()` dumps. The tool produced output stylistically
indistinguishable from a 2010-era CLI even though every modern CLI
(`pip`, `poetry`, `pdm`, `uv`, `pytest`, `gh`) had moved on to
[Rich](https://github.com/Textualize/rich).

Two structural risks blocked a naive adoption:

- **Markup leak.** If Rich's `[bold red]ERROR[/bold red]` markup or
  ANSI escape codes reached `FileLog`, the text/JSON/HTML files would
  ship with terminal control sequences embedded — corrupting machine
  parsers and confusing human readers.
- **stdout contract.** ADR-0005 / ADR-0008 reserve stdout for machine
  payloads (`--format json`, `sarif`, etc.). Any Rich rendering that
  leaked to stdout would break those contracts.

## Decision drivers

- Modernise console UX without disturbing files / JSON / HTML
  consumers.
- Preserve the stdout contract from ADR-0005 / ADR-0008.
- Keep tests green: 8000+ unit tests, many using `capsys` to grep
  stderr for substrings (`assert "ERROR:" in captured.err`).
- Use a dependency that already ships in the runtime requirements
  (`rich>=13.3.0` was declared but unused).
- Keep the surface small: one module that owns console plumbing,
  reused by every sink.

## Considered options

1. **Wire Rich at the `ConsoleLog` sink only; keep formatters
   plain-text.** A shared `core/logger/console.py` exposes a
   singleton `Console(stderr=True)`, severity Theme, and pure-text
   render helpers (`render_table_to_str`, `render_tree_to_str`,
   `render_panel_to_str`).
2. Push Rich into `TextFormatter` so all sinks share one renderer.
   **Rejected** — markup would leak into files and break the JSON /
   HTML contract.
3. Introduce a parallel `RichConsoleLog` and let users opt in via
   config. **Rejected** — fragments the code path and forces every
   command to know which logger they hold.
4. Replace `Log` entirely with `rich.logging.RichHandler`. **Rejected**
   — would force a full rewrite of `MultiLog`, `FileLog`, the
   JSON / HTML formatters, and 1000+ test mocks.

## Decision outcome

Chosen option: **option 1**.

### Module layout

`core/logger/console.py` owns:

- `DBLIFT_THEME` — severity styles (`log.debug`, `log.info`,
  `log.warn`, `log.error`, `log.notice`).
- `get_stderr_console()` — singleton `Console(stderr=True,
  theme=DBLIFT_THEME)`. Single instance shared across `ConsoleLog`,
  `rich.progress.Progress`, `rich.traceback.install`, and
  `Console.status(...)` spinners. Rich resolves `sys.stderr` lazily,
  so `capsys` monkeypatching keeps working.
- `render_to_str` / `render_table_to_str` / `render_tree_to_str` /
  `render_panel_to_str` — render any Rich `RenderableType` to a
  **plain-text string** via `Console.capture()` with
  `force_terminal=False, no_color=True`. The resulting string
  contains no ANSI / markup and is safe for files / pipes / `log.info`.
- `install_rich_traceback()` — installs Rich's pretty traceback as
  `sys.excepthook`, writing to the same stderr Console. Honours
  ADR-0008 (no stdout pollution).

### Sinks and styling boundary

`TextFormatter` is **unchanged**. It continues to produce plain
text like `"ERROR: connection refused"`. The same `format_event`
output flows into `FileLog` (text/JSON/HTML) and `ConsoleLog`.

`ConsoleLog._write_log_event` is the single place that applies
severity styling: it picks a style from `_LEVEL_STYLES` (mapping
`LogLevel` → theme key) and calls
`self._console.print(formatted_msg, style=style, markup=False,
highlight=False)`. Styling happens at print time, not in the
formatter, so `markup=False` prevents accidental interpretation of
square-bracketed message content.

### Two new logger channels

- `Log.console_print(renderable)` — emit a Rich `RenderableType`
  (Syntax, Tree, Panel, Table, ...) **only** to `ConsoleLog`.
  `MultiLog` forwards to each `ConsoleLog` child; `FileLog` /
  `NullLog` no-op. Used by `_handle_diff` to syntax-highlight the
  generated SQL on the terminal without leaking ANSI to the
  text / JSON / HTML logs.
- `Log.file_only_info(message)` — symmetric counterpart: emit a plain
  message to `FileLog` children, skip the console. Pairs with
  `console_print` so the same content reaches every sink in its
  appropriate form.

### Wiring

| Surface | Module / line | Rich feature |
|---|---|---|
| Severity styling | `core/logger/log.py` `ConsoleLog._write_log_event` | `Console.print(style=...)` |
| Migration history table | `core/migration/state/migration_formatter.py` | `rich.table.Table` |
| Query-result table | `core/migration/ui/table_renderer.py` | `rich.table.Table` |
| Migration-list table | `core/migration/ui/table_renderer.py` | `rich.table.Table` |
| Migration loop progress | `core/migration/commands/migrate_command.py` | `rich.progress.Progress` |
| Snapshot / export-schema | `core/migration/commands/{snapshot,export_schema}_command.py` | `Console.status(...)` |
| Diff header / footer / summary | `core/migration/commands/diff_command.py` | `rich.panel.Panel` |
| Diff hierarchy (15 object types) | `core/migration/commands/diff_command.py` | `rich.tree.Tree` |
| Command completion footer | `core/migration/commands/base_command.py` | `rich.panel.Panel` |
| Generated SQL preview | `cli/_command_handlers.py::_handle_diff` | `rich.syntax.Syntax` (console only) + `file_only_info` (files) |
| Uncaught exceptions | `cli/main.py` | `rich.traceback.install` + `Console.print_exception` |

### What stays unchanged

- `TextFormatter`, `JsonFormatter`, `HtmlFormatter` — all produce
  raw text / structured payloads. No markup leak risk.
- `cli/_output.py::CommandOutput` — ADR-0008 stdout/stderr router
  keeps its current contract. `CommandOutput.machine(payload)` still
  writes raw JSON / SARIF to stdout. Rich is invisible to the
  machine path.
- ADR-0005 — banner suppression for machine formats remains in
  effect.

### Removed dependency

`prettytable>=3.5.0` is dropped from `pyproject.toml`,
`requirements.txt`, and `requirements-runtime.txt`. Zero remaining
imports.

## Positive consequences

- Modern, scannable console UX: severity colour, Unicode box tables,
  hierarchical trees for diffs, status spinners for long ops, pretty
  tracebacks.
- File logs (text / JSON / HTML) keep their exact previous shape —
  no consumer breaks.
- ANSI codes auto-disable in non-tty contexts (CI logs, pipes,
  `capsys`), so the existing `capsys.readouterr().err` substring
  assertions across 8000+ tests still pass.
- Single Console instance prevents redraw conflicts when Progress and
  log lines interleave.
- Drops a runtime dependency (`prettytable`).

## Negative consequences

- Adds Rich to the import graph of `core/logger/log.py`. Rich is
  pure Python, MIT-licensed, ~few-MB shipped (already in
  PyInstaller binary distributions).
- Diff command emits one combined Tree per object-type section
  instead of N flat `log.info` calls. Tests that mocked `log.info`
  by call count would have broken; we audited and found none. New
  tests should assert on output substrings, not `log.info` call
  counts.

## Follow-ups

- Migrate `cli/license_commands.py` and `cli/db_utils.py` from
  direct `print()` to `cli/_output.py::CommandOutput` once the
  surrounding tests have been audited (currently outside the
  `cli-print-stdout` lint scope, no behavioural delta).
- Drop `CommandOutput`'s `human-mode → stdout` branch for
  `status` / `banner` once ADR-0008's "Full stderr routing"
  follow-up lands. Requires a sweep across every test that greps
  `captured.out` for log lines.
- Wire `--no-progress` / `--quiet` CLI flags now that Progress and
  styling have a single integration point.
- Future iterations can layer `rich.live`, `rich.markdown`, or
  per-table `rich.progress.track` without touching call sites — the
  helpers and channels are in place.

## Links

- `core/logger/console.py` — the helpers and singleton
- `core/logger/log.py` — `ConsoleLog`, `MultiLog.console_print`,
  `MultiLog.file_only_info`, `FileLog.file_only_info`
- `tests/unit/core/logger/test_console.py` — unit tests
- [ADR-0005](0005-stdout-machine-readability.md) — stdout contract
- [ADR-0008](0008-command-output-abstraction.md) — `CommandOutput`
  abstraction (interacts via the unchanged stdout contract)
