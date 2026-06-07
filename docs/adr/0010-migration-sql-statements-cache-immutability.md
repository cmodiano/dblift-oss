# 0010 — `Migration._sql_statements` is canonical-only; ``content_override`` does not poison the cache

- Status: Accepted
- Date: 2026-04-19
- Deciders: Maintainers

## Context and problem statement

``Migration.parse_sql_statements`` accepts an optional
``content_override`` parameter so the execution engine can pass
placeholder-substituted SQL into the tokeniser (BUG-06 fix from the
1.3.1 release-test). Without that bypass the tokeniser would split
``${schema}_users`` into two tokens (``${schema} _users``) and produce
unparseable SQL.

Bugbot on PR 160 (file ``core/migration/migration.py`` line 386,
discussion ``r3106139670``) flagged that the implementation also wrote
the parsed result back into ``self._sql_statements`` regardless of
which content was parsed. The consequence:

- After execution, the migration object's ``_sql_statements`` cache
  holds the **placeholder-substituted** statements (e.g.
  ``CREATE TABLE app_users (...)``).
- Any later reader — checksum recomputation, ``info`` display, repeat
  ``parse_sql_statements()`` call without override — observes the
  substituted form instead of the canonical one (e.g.
  ``CREATE TABLE ${schema}_users (...)``).
- The Migration object's observable state is execution-tainted; the
  same migration looks different before and after a run.

## Decision drivers

- The Migration's canonical state is its source content. Anything
  derived from a per-execution substitution is a transient detail of
  *that* execution, not a property of the migration.
- Checksum and audit semantics rely on canonical content. A poisoned
  cache silently changes those answers.
- The PR-04 lint rule (``enum-str-conversion``) caught a related
  pattern; this one is the same family — observable state mutated by
  what looks like a read.

## Considered options

1. **Skip the cache write when ``content_override`` is provided** (this
   ADR). The function still returns the parsed override result, but
   does not update ``self._sql_statements``.
2. Make ``Migration`` fully immutable: a frozen dataclass-style object
   with a separate ``parser`` service. Cleaner long-term but a much
   larger refactor — touches every call site that reassigns
   ``migration.type`` / ``migration.checksum`` / ``migration.success``.
   Deferred.
3. Compute statements on every call without caching at all. Simpler
   but penalises callers that legitimately re-read on the same
   instance (e.g. validation pre-flight then execution).
4. Do nothing. Document the foot-gun in the docstring. Rejected — the
   stabilisation programme's goal is to remove the foot-guns, not
   document them.

## Decision outcome

Chosen option: **option 1**. Implementation:

```python
def parse_sql_statements(self, dialect=None, content_override=None):
    content = content_override if content_override is not None else self.content
    cache_result = content_override is None    # <-- the gate
    ...
    statements = sql_analyzer.split_statements(content)
    if cache_result:
        self._sql_statements = statements
    return statements
```

The contract is now simple and testable:

- ``parse_sql_statements()`` (no override) — caches the canonical-content
  parse on ``self._sql_statements``. Behaviour unchanged.
- ``parse_sql_statements(content_override=...)`` — returns the parsed
  override result; ``self._sql_statements`` is untouched.
- Therefore ``self._sql_statements`` is always either ``None`` or a
  parse of ``self.content`` — never a substituted form.

### Tests

``tests/unit/core/migration/test_migration_immutability.py`` (new) —
9 assertions:

- override leaves a never-touched cache as ``None``;
- override does not overwrite a pre-existing canonical cache;
- a fresh no-override parse after an override returns canonical
  statements (the headline user-facing symptom);
- canonical caching still works (regression);
- the ``sql_statements`` property (which always recomputes from
  ``self.content``) is observably independent;
- empty override falls back without poisoning.

Full migration unit suite: 779 passed, 1 skipped. No regression.

### Positive consequences

- ``Migration`` no longer carries execution-tainted state across
  reads. Checksum / info / audit see canonical content
  unconditionally.
- The stale-state bug class (Bugbot PR 160 line 386) is closed at
  the source, not just patched at the Bugbot-flagged line.
- The contract is one ``if cache_result:`` line — easy to audit, hard
  to regress.

### Negative consequences

- Callers that previously relied on the side-effect of "after I
  execute, ``_sql_statements`` holds what I just executed" will see
  ``None`` (or the canonical parse). No code in this repository
  relied on that side-effect — the call sites in
  ``core/migration/executor/execution_engine.py`` and
  ``core/migration/executors/sql_executor.py`` consume the *return*
  value, not the cached one.

## Follow-ups

- Option 2 (full Migration immutability via a frozen dataclass) is
  worth a separate ADR. It subsumes this one and would also fix the
  scattered mutations of ``type`` / ``success`` / ``execution_time``
  observed during execution. Deferred until the more disruptive scope
  is justified.

## Links

- ``core/migration/migration.py`` — implementation
- ``tests/unit/core/migration/test_migration_immutability.py`` — contract tests
- Bugbot thread PR 160 line 386 — original flag
- ``docs/stabilization-plan.md`` — Phase 2 PR-10
