# 0009 — Argparse parent parsers for shared CLI flag clusters

- Status: Accepted
- Date: 2026-04-19
- Deciders: Maintainers

## Context and problem statement

Three BUGs on the 1.3.1 release (`BUG-01`/`02`/`05`) were all caused
by the same shape: a top-level argparse argument silently overwritten
by a subparser that redeclared the same ``dest``. Commit `bb47769`
fixed the instances (`--config`, `--scripts`, later `--dry-run`), and
``tests/unit/cli/test_parser_invariants.py`` (PR-03) now enforces the
invariant via 210 parametrised cases plus a structural walker test.

However, ``cli/_parser_setup.py`` still imperatively added several
argument clusters with ``for subparser in [...]: subparser.add_argument(...)``
loops:

- ``--table`` on 8 subparsers (migrate, undo, clean, validate, info,
  diff, repair, import-flyway, plus a locally duplicated version on
  baseline)
- ``--strict`` on 7 subparsers (same minus import-flyway)
- ``--tags``, ``--exclude-tags``, ``--versions``, ``--exclude-versions``,
  ``--placeholders`` on 5 subparsers (migrate, undo, validate,
  info, diff)
- ``--target-version`` on 3 subparsers (migrate, undo, diff)

This pattern works today but is the ancestor of the BUG-01 family —
any future contributor editing the list is one typo away from a
re-introduction. The argparse-native remedy is ``parents=[...]``.

## Decision drivers

- Make the inheritance visible at the call site
  (``subparsers.add_parser(..., parents=[_history, _strict])``) instead
  of encoded in a loop 20 lines away.
- Eliminate the drift risk between a "membership list" and the actual
  parsers affected.
- Keep the change surface minimal: ``parents=[...]`` is an argparse
  primitive, no new abstractions, no framework.

## Considered options

1. **Extract 4 parent parsers** (``_history``, ``_strict``, ``_filter``,
   ``_target_version``) and wire them in each subparser's ``parents=``
   list. This ADR.
2. Build a full declarative spec (``COMMANDS = {...}``) and drive the
   whole parser tree from data. Larger change, same test outcome, more
   risk of unknown-unknowns. Deferred (see "Follow-ups").
3. Leave the imperative loops and rely on PR-03's invariants tests to
   catch mistakes. The tests do catch duplicate ``dest``, but they
   don't catch "this cluster was forgotten on a new subcommand".
4. Merge the sub-parsers with deep inheritance trees (one giant
   ``_migration_parent``). Reduces ``parents=`` boilerplate but hides
   which cluster each subparser actually exposes.

## Decision outcome

Chosen option: **option 1**.

### Parent parsers introduced

```python
_make_history_table_parent()   # --table            (9 subcommands)
_make_strict_parent()          # --strict           (7 subcommands)
_make_filter_parent()          # tag/version/placeholder filters (5)
_make_target_version_parent()  # --target-version   (3 subcommands)
```

Each is a factory returning a fresh ``ArgumentParser(add_help=False)``
with exactly the flags in its cluster. Subparsers declare inheritance
at construction time:

```python
migrate_parser = subparsers.add_parser(
    "migrate",
    help="Apply migrations",
    parents=[_history, _strict, _filter, _tgt],
)
```

### What got deleted

- The two ``for subparser in [...]`` loops inside
  ``_add_common_migration_args`` (25 lines).
- The three per-command ``migrate_parser.add_argument("--target-version", ...)``
  lines inside ``_add_diff_and_target_options``.
- The duplicated ``--table`` in ``_add_baseline_options`` (baseline now
  inherits ``_history`` too).

``_add_common_migration_args`` was kept as a no-op immediately after
PR-09 for backward compatibility, then removed in a follow-up cleanup
PR once no in-tree test/import referenced it. Bugbot flagged the no-op
as misleading (the call site passed eight parsers, suggesting it
configured them) — the fix was simply to delete both the definition
and the call.

### Positive consequences

- ``subparsers.add_parser(..., parents=[_history, _strict])`` states in
  one place what the subcommand inherits. No need to cross-reference a
  list 20 lines below.
- Cannot silently add a 9th ``--strict``-supporting subcommand and
  forget the loop membership — you either add ``parents=[_strict]`` or
  the flag is absent.
- The 210 cases of ``test_parser_invariants.py`` (PR-03) still pass
  unchanged: ``parents=[...]`` is exactly what
  ``test_walker_allows_parents_inheritance`` documents as the non-bug
  shape.
- 470 CLI unit tests pass in regression.

### Negative consequences

- File is marginally longer (535 vs 475 lines) because each parent
  factory carries a docstring explaining its cluster. The growth is
  documentation, not code.

## Follow-ups

- Option 2 (fully declarative spec) can land later on top of this
  change without further argparse churn.

## Links

- `cli/_parser_setup.py` — the refactored parser builder
- PR-03 ADR-less commit — the invariants test that protects this PR's
  output
- `tests/unit/cli/test_parser_invariants.py` — the 210 cases that
  passed unchanged
- `docs/stabilization-plan.md` — Phase 2 PR-09
