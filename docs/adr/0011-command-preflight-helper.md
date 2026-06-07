# 0011 — `_run_preflight()` centralises the connect/history/populate sequence

- Status: Accepted
- Date: 2026-04-19
- Deciders: Maintainers

## Context and problem statement

Every migration command opens with some combination of three phases:

1. ``_ensure_connected()`` — open/verify the provider connection.
2. ``history_manager.create_schema_and_history_table()`` — idempotent
   DDL for the ``dblift_schema_history`` table (skipped in dry-run).
3. ``_populate_database_info(result)`` — stamp the result with live
   connection metadata (version, database URL, driver).

The order matters: ``_populate_database_info`` calls provider methods
that require a live connection, and ``create_schema_and_history_table``
depends on the connection being live. Before this ADR, the three calls
were open-coded in each command, and the order drifted:

- ``migrate_command.execute``: connect → (skip in dry-run)
  create_history → populate. Correct.
- ``clean_command.execute``: connect (with an explicit try/except for
  non-dry-run tolerance) → set_current_schema → populate. Correct but
  uses a clean-specific error policy.
- ``info_command.execute``: **populate → create_history**. Wrong order.
  Bugbot flagged this on PR 160 (*"Database info populated before
  connection is established"*). It happened to work in practice
  because the provider's ``_populate_database_info`` internally calls
  ``_ensure_connection`` as a fallback — but that defensive fallback
  is what let the latent bug live.

Any future command that re-opens this sequence has a non-trivial
chance of mis-ordering it.

## Decision drivers

- Encode the canonical order once, in the base class, so misordering
  is structurally impossible in commands that adopt the helper.
- Keep the change surgical. The full ``CommandLifecycle`` with hooks
  (option A in the plan) is a much bigger refactor; option B captures
  90 % of the value with 10 % of the risk.
- Pin the contract in unit tests so a future "simplification" cannot
  silently reorder the phases.

## Considered options

1. **Introduce ``_run_preflight(result, *, ensure_history, dry_run)``
   on ``BaseCommand``** (this ADR). ``migrate``, ``info`` adopt it;
   ``clean`` keeps its bespoke error policy.
2. Full ``CommandLifecycle`` with ``connect → preflight → execute →
   teardown`` hooks registered per command. Architecturally cleaner
   but requires touching four command files (migrate 646 lines, clean
   431, info 227, export-schema 1874) and re-threading how transactions
   / locks / callbacks hang off the lifecycle.
3. Leave the phases inline in each command, fix info's order once,
   hope nobody reintroduces the drift. Rejected — the goal of the
   stabilisation programme is to remove foot-guns, not re-step on them.
4. Ban open-coded phases via lint rule (``_populate_database_info``
   may only be called from within ``BaseCommand._run_preflight``).
   Over-engineered for two call sites.

## Decision outcome

Chosen option: **option 1**.

```python
def _run_preflight(self, result, *, ensure_history=False, dry_run=False):
    self._ensure_connected()
    if ensure_history and not dry_run:
        self.history_manager.create_schema_and_history_table(create_schema=False)
    self._populate_database_info(result)
```

### Adopted by

- ``info_command.execute`` — ``_run_preflight(result, ensure_history=True)``.
  Fixes the Bugbot-flagged order bug.
- ``migrate_command.execute`` — ``_run_preflight(result,
  ensure_history=True, dry_run=dry_run)``. Identical behaviour,
  three calls collapsed into one.

### Not adopted

- ``clean_command.execute`` — has a bespoke error policy
  (``_ensure_connected`` errors are swallowed in non-dry-run mode,
  re-raised in dry-run). Forcing it through the helper would either
  duplicate that policy everywhere or hide it. clean remains inline
  with a comment noting the deliberate deviation.
- ``export_schema_command`` — 1874-line command with its own shape;
  out of scope for this PR. Safe to leave: it has its own (passing)
  integration tests.

### Tests

``tests/unit/core/migration/commands/test_preflight_ordering.py`` (new) —
four parametrised assertions pinning the contract:

- default (no history) = connect → populate
- with history = connect → create_history → populate
- dry_run skips create_history regardless of ``ensure_history``
- populate always runs after connect under every flag combination

Regression: 783 passed, 1 skipped on the full migration unit suite
(was 779 + 4 new ordering tests = 783; the pre-existing single skip
is unrelated to this change).

### Positive consequences

- ``info_command`` no longer has the phases in the wrong order.
- Future commands that adopt the helper cannot reintroduce the bug
  family.
- The contract is executable, not documentary: the ordering tests
  fail if anyone reorders the three calls inside ``_run_preflight``.

### Negative consequences

- Two command files out of four lose their explicit three-line
  preflight in favour of a single method call. The call name
  (``_run_preflight``) and its docstring carry the contract — readers
  have to look up the helper to understand what phases run. Mitigated
  by the docstring linking to this ADR.

## Follow-ups

- ``export_schema_command`` is a natural next candidate for adoption
  once its own preflight is audited. Left as a separate PR because
  the file's size makes the risk vs reward unfavourable for a combined
  change.
- Option 2 (full ``CommandLifecycle``) remains the long-term target
  if per-command drift re-emerges or the number of phases grows.

## Links

- ``core/migration/commands/base_command.py`` — the helper
- ``core/migration/commands/info_command.py``,
  ``core/migration/commands/migrate_command.py`` — adopters
- ``tests/unit/core/migration/commands/test_preflight_ordering.py`` —
  contract tests
- Bugbot thread PR 160 — "Database info populated before connection
  is established"
- ``docs/stabilization-plan.md`` — Phase 2 PR-11
