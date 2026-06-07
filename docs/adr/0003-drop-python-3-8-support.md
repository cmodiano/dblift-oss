# 0003 — Drop Python 3.8 support

- Status: **Superseded by [0004](0004-bump-minimum-python-to-3-11.md)**
  on 2026-04-19
- Date: 2026-04-19
- Deciders: Maintainers
- Supersedes: none

> **Note:** This ADR was superseded within hours of its acceptance once
> the implementation PR (PR-0G) surfaced that the codebase already
> required Python 3.11+ features. See ADR-0004 for the corrected
> analysis and decision. This file is kept for historical record.

## Context and problem statement

PR-0E baseline run of `pip-audit` against current dependency floors
surfaced 17 known CVEs across 5 packages, including 7 CVEs in
`cryptography`. Fixing all of them requires `cryptography >= 46.0.6`,
which itself requires **Python 3.9+**.

`pyproject.toml` currently declares:

```toml
requires-python = ">=3.8"
```

with classifiers for 3.8, 3.9, 3.10, 3.11.

Python 3.8 reached end-of-life on **2024-10-07**. At the time of this
ADR (2026-04-19) it has been unsupported by upstream for 18 months.
Python 3.9 reached end-of-life on **2025-10-31** (6 months ago); the
project could drop it as well but that is a larger change and is
deferred.

## Decision drivers

- Security: cannot close 3 of the 5 `cryptography` CVEs while supporting
  Python 3.8.
- Due diligence: supporting EOL runtimes is flagged in nearly every
  technical DD checklist.
- Maintenance burden: every new dependency bump has to re-verify 3.8
  compatibility, and several modern libraries (e.g. `cryptography` 43+,
  `setuptools` 78+, future `PyJWT`) have already dropped it.
- User impact: users still on Python 3.8 will need to upgrade the
  interpreter to install a new `dblift`. Python 3.9, 3.10, 3.11, 3.12,
  3.13 are all available on supported OSes.

## Considered options

1. **Drop Python 3.8**, bump dependency floors, keep 3.9+.
2. Keep Python 3.8, pin `cryptography < 43` and accept 3 unfixed CVEs
   (plus the others from `setuptools` / `wheel`).
3. Drop Python 3.8 **and 3.9** together, targeting 3.10+ (Python 3.9 is
   also EOL).
4. Fork the codebase: `legacy/1.x` line stays on 3.8, `main` drops it.

## Decision outcome

Chosen option: **option 1 — drop Python 3.8**.

Rationale:

- Option 2 is incompatible with the stabilization program's security
  target (zero known CVEs in runtime deps).
- Option 3 is correct long-term but disruptive for users still on 3.9
  (6 months out of EOL, likely most users). Keep as a follow-up ADR.
- Option 4 doubles the maintenance surface during a stabilization
  program whose goal is to *reduce* maintenance surface.

### Changes

- `pyproject.toml`:
  - `requires-python = ">=3.9"`
  - Drop `"Programming Language :: Python :: 3.8"` classifier
  - Bump `cryptography >= 46.0.6`
  - Bump `PyJWT >= 2.12.0`
  - Build-system: `setuptools >= 78.1.1`, `wheel >= 0.46.2`
- `[tool.black]`: drop `py38` from `target-version`
- `[tool.mypy]`: `python_version = "3.9"` (lowest supported)
- `CHANGELOG.md`: record the drop in the Unreleased section as a
  BREAKING CHANGE.

### Positive consequences

- All 17 known CVEs in runtime deps closable in the same PR.
- One fewer runtime to test against in CI.
- Unlocks type-hint syntax that required `__future__` imports on 3.8
  (`dict[str, int]`, `list[T]`, PEP 604 unions eventually via 3.10+).

### Negative consequences

- Breaking install change for any user still on Python 3.8. Mitigation:
  announce in the v1.4.0 release notes with a 3-line upgrade guide.
- Any CI job matrix element targeting 3.8 must be removed.

## Links

- Python 3.8 EOL: https://devguide.python.org/versions/
- `docs/stabilization-plan.md` — "Known dependency CVEs"
- PR-0E baseline run output
