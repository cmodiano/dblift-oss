# 0002 — Stabilization program instead of new features until v2.0

- Status: Accepted
- Date: 2026-04-19
- Deciders: Maintainers

## Context and problem statement

Between v1.1.0 and v1.3.1, 41 out of 94 commits on this repository were
bug fixes (~44 %). The 1.3.1 release test surfaced 8 bugs in a single
pass (`BUG-01` through `BUG-08`, resolved in commit `bb47769`). PR
reviews by Bugbot have continued to surface families of regressions
(enum vs string comparison on `MigrationType`, duplicate argparse
declarations, stdout contamination by the logger, placeholder
substitution paths, connection lifecycle drift).

Root cause analysis points to **incomplete refactors** rather than
accidental bugs: new helpers and constants are introduced without
purging legacy call sites, so two versions of the same logic cohabit
and drift until a future bug surfaces the divergence.

The product is planned for commercial distribution; external technical
due diligence will assess maintainability, test coverage, architectural
consistency, and bug history. The current trajectory is not audit-ready.

## Decision drivers

- Commit history is public. A 44 % fix ratio is a strong negative
  signal in technical due diligence.
- Continuing to add features while bugs regenerate in the same modules
  creates compounding debt.
- The refactors required (unify `MigrationType`, eliminate argparse
  duplication, extract `CommandLifecycle`) are cross-cutting and cannot
  be safely done in parallel with unrelated feature work.

## Considered options

1. **Freeze new features** until stabilization targets are met.
2. Continue features in parallel with fixes.
3. Fork a "v2" branch for stabilization; keep `main` feature-active.

## Decision outcome

Chosen option: **Freeze new features**.

The freeze holds until the targets in `docs/stabilization-plan.md` are
met:

- Rolling 3-month fix ratio below 15 %
- Zero unresolved Bugbot `High`/`Medium` threads on merge for two
  consecutive weeks
- Phase 2 refactors (PR-06 through PR-11) all merged
- Coverage floor raised to ≥ 85 %

A `feat:` PR during the freeze is rejected by default. Exceptions
require a new ADR superseding this one, with explicit justification.

### Positive consequences

- Focuses all contributor effort on closing the instability loop.
- Produces the documentation (ADRs, `ARCHITECTURE.md`, stabilization
  plan) expected at due diligence.
- Every refactor PR ships both code and the test/lint gate that
  prevents the pattern's return.

### Negative consequences

- No new user-facing functionality for ~2-3 months.
- If a competitor ships a feature during the freeze, market pressure
  will push for lifting the freeze — the ADR must then be explicitly
  superseded, not silently ignored.

## Links

- `docs/stabilization-plan.md`
- `CONTRIBUTING.md`
