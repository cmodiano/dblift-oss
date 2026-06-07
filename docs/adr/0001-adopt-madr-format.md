# 0001 — Adopt MADR format for ADRs

- Status: Accepted
- Date: 2026-04-19
- Deciders: Maintainers

## Context and problem statement

The project is about to undertake structural refactors (see
`docs/stabilization-plan.md`, Phase 2). Without a record of the
decisions, future contributors and external auditors have to
reverse-engineer the rationale from diffs — which is the situation that
allowed the current cohabitation of legacy and new call sites
(`VERSIONED_SCRIPT_TYPES` duplicated in three modules, `_ensure_connected`
inlined versus base-class, etc.).

## Decision drivers

- External due diligence will look for ADRs as evidence of engineering
  discipline.
- Contributors need a stable shape to follow.
- The format should be low friction: markdown, in the repository, no
  tooling dependency.

## Considered options

1. [MADR](https://adr.github.io/madr/) — widely adopted, markdown.
2. Nygard-style ADRs — the original, simpler but less structured.
3. RFCs in a separate repository — used by larger organizations.
4. No ADRs; rely on PR descriptions — status quo.

## Decision outcome

Chosen option: **MADR**.

- Provides a consistent structure (Context / Drivers / Options /
  Outcome / Consequences) that forces the author to consider
  alternatives rather than justify only the chosen path.
- Renders natively on GitHub.
- Template is short enough that the overhead is negligible.

### Positive consequences

- Every structural PR cites an ADR.
- Auditors have a single directory to read.
- Decisions are immutable once merged; changes require a new ADR
  superseding the old one — the history is explicit.

### Negative consequences

- Small overhead per structural change. Acceptable given the current
  cost of unrecorded decisions.

## Links

- https://adr.github.io/madr/
- `CONTRIBUTING.md` — "Architecture Decision Records"
