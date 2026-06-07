# 0004 — Bump minimum Python to 3.11

- Status: Accepted
- Date: 2026-04-19
- Deciders: Maintainers
- Supersedes: [0003](0003-drop-python-3-8-support.md)

## Context and problem statement

ADR-0003 chose to drop Python 3.8 support (option 1) in order to close
the `cryptography` CVE chain, and deferred dropping Python 3.9 as "too
disruptive in one change." In the implementation PR (`8daf1e8`, PR-0G)
we changed `mypy.python_version` from `"3.11"` to `"3.9"` to align the
type checker with the declared `requires-python = ">=3.9"`.

CI then failed with 40 mypy errors. Investigation showed the code
already uses features that are not available on Python 3.9 or 3.10:

| Feature | Minimum Python | Count | Locations |
|---|---|---|---|
| PEP 604 unions (`X \| Y` in annotations) | 3.10 | 31 | `db/jdbc_provider.py`, `db/plugins/oracle/provider.py`, `db/plugins/db2/provider.py`, `db/introspection/vendor_queries_base.py` |
| `@dataclass(slots=True)` | 3.10 | 4 | `core/migration/state/migration_state_manager.py`, others |
| `typing.Self` | 3.11 | 1 | `api/client.py` |

None of the affected files carry `from __future__ import annotations`
(except `migration_state_manager.py`, where the blocker is the runtime
`slots=True` keyword, which `__future__` does not defer). The code
therefore **does not run on Python 3.9 or 3.10** — the `requires-python`
declaration of `">=3.8"` (before PR-0G) and `">=3.9"` (after PR-0G) were
both factually incorrect.

CI matrix in `.github/workflows/unit-tests.yml` already tests only
Python 3.11 and 3.12, so no green run on 3.9/3.10 ever existed.

## Decision drivers

- **Honesty**: `requires-python` should reflect what the code runs on,
  not aspirational support.
- **Security**: the CVE chain from ADR-0003 remains closed (requires
  `cryptography >= 46.0.6` which needs 3.9+).
- **Maintenance**: refactoring ~36 call sites to be 3.9-compatible
  (replace `str | int` with `Union[str, int]`, remove `slots=True`,
  import `Self` from `typing_extensions`) is pure regression work for
  a runtime we neither test against nor have users on.
- **Python 3.9, 3.10 EOL status**:
  - 3.9 EOL: 2025-10-31 (6 months ago)
  - 3.10 EOL: 2026-10-04 (5 months out)
- **Upstream alignment**: tools the project depends on are also moving.
  `cryptography` 46 requires 3.9+; NumPy, SciPy, and other SPEC 0
  signatories follow a 24-36 month window.

## Considered options

1. **Bump `requires-python` to `>=3.11`** to match factual usage.
2. Refactor the 36 call sites to be Python 3.9-compatible, keep
   `requires-python = ">=3.9"`.
3. Split the difference: `requires-python = ">=3.10"`, refactor only
   the single `typing.Self` import.
4. Keep 3.9 declared but unsupported; ignore mypy errors.

## Decision outcome

Chosen option: **option 1 — `requires-python = ">=3.11"`**.

Rationale:

- Options 2 and 3 fund ongoing work to support runtimes that are EOL
  or imminently EOL, and that no CI job exercises.
- Option 4 leaves a known-false declaration in `pyproject.toml`, which
  is the opposite of the stabilization program's principle of encoding
  invariants in CI rather than in intent.
- CI already tests only 3.11 and 3.12 (matrix in `unit-tests.yml`).
  Declaring 3.11 minimum matches the test matrix.

### Changes

- `pyproject.toml`:
  - `requires-python = ">=3.11"`
  - Classifiers: keep only `3.11`; drop `3.9`, `3.10`
- `[tool.black] target-version = ['py311']`
- `[tool.mypy] python_version = "3.11"` (revert of PR-0G change)
- `CHANGELOG.md` Unreleased: update the BREAKING CHANGE to reflect the
  final minimum.

No source-code changes are required (the code already uses 3.11
features).

### Positive consequences

- `requires-python` is now factually correct.
- All 40 mypy errors introduced by PR-0G's `python_version = "3.9"` are
  resolved.
- One runtime version to maintain instead of three.

### Negative consequences

- Users still on Python 3.9 or 3.10 cannot install `dblift >= 1.4.0`.
  Mitigation: they couldn't run the existing code anyway (it would fail
  at import with `TypeError: unsupported operand type(s) for |`).
  The v1.4.0 release notes will document the hard minimum.

## Links

- [ADR-0003](0003-drop-python-3-8-support.md) (superseded)
- `docs/stabilization-plan.md`
- Python release schedule: https://devguide.python.org/versions/
