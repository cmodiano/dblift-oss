# Stabilization plan (v1.3.x → v2.0)

## Context

Between v1.1.0 and v1.3.1, 41 of 94 commits on this repository were `fix`
commits (~44 %). The 1.3.1 release testing alone surfaced 8 bugs
(`BUG-01` through `BUG-08`, resolved in commit `bb47769`). Recent PR
reviews by Bugbot surfaced additional families of regressions around
CLI argument routing, JSON output contamination, `MigrationType` enum
versus string comparison, and migration execution lifecycle.

The root cause analysis concluded that the instability is driven less by
accidental bugs than by **incomplete refactors**: new helpers and
constants are introduced without purging the legacy call sites, so two
versions of the same logic cohabit until a future bug surfaces the
drift.

The goal of this program is to:

1. Close the enforcement gap in CI so regressions cannot silently merge.
2. Finish the refactors that generate recurring bugs.
3. Produce the documentation and artefacts expected at due diligence.

**Features are frozen during the program.** Only items in this plan (or
fixes with a regression test) are accepted.

## Horizons

### Phase 0 — Enforcement scaffold

| PR | Status | Scope |
|---|---|---|
| PR-0A | merged (`3963b94`) | `code-quality.yml` triggers on every `pull_request` |
| PR-0C | merged (`41fe4e6`) | `.flake8` ignore list reduced from 23 to 8 rules; 9 trailing violations fixed |
| PR-0E | merged (`56e870e0`) | `bandit`, `pip-audit`, `gitleaks`, `xenon` complexity budget as blocking gates |
| PR-0F | merged | `CONTRIBUTING.md`, PR template, ADR scaffold |
| PR-0G | merged (`8daf1e83`) | Dependency-floor bump closing 17 known CVEs across `cryptography`, `PyJWT`, `setuptools`, `wheel`; Python 3.8 dropped in the same move (see ADR-0003) |
| PR-0B | deferred | Coverage floor (currently 77 %, tracked in Codecov, not yet blocking) |
| PR-0D | deferred | Mypy strict mode per module (currently gradual adoption) |

### Phase 1 — Functional regression gates

Each item = one PR introducing a test that fails against the pre-fix
commit and passes today (retroactive proof).

| PR | Status | Target |
|---|---|---|
| PR-01 | merged | CLI subprocess stdout contract — extend `tests/integration/matrix/test_json_output_contract.py` to cover `validate-sql --format json` (was collaterally broken by 217a5694). Add new workflow `matrix-tests.yml` that runs the matrix regression suite on every `pull_request` — deliberately isolated from `integration-tests-new.yml` (20-min full DB suite stays `workflow_dispatch` to respect the Actions minute budget). |
| PR-02 | merged | `--dry-run` purity — add `tests/integration/matrix/test_dry_run_purity.py` asserting byte-identical DB before/after for both `migrate --dry-run` and `clean --dry-run`. Strictly stronger than the existing enumerated checks (catches any future BUG-class of the history-table-creation family). |
| PR-03 | merged | Parameterized "global args preserved" test — extend `tests/unit/cli/test_parser_invariants.py` coverage to include `--license-key` and `--log-file` (historical regression sources); add self-maintaining meta-property `test_every_top_level_flag_is_covered_or_exempted` so any future top-level flag either lands in the covered set or requires an explicit exempt entry. |
| PR-04 | merged | AST-based lint patterns — add `scripts/lint_patterns.py` with two rules: `cli-print-stdout` (stdout contract for `cli/main.py` and `cli/_command_handlers.py`) and `enum-str-conversion` (the `str(migration_type)` / `str(x.type)` anti-pattern). Ratchet via `.lint-patterns-baseline.txt`: 29 existing `enum-str-conversion` entries listed as TODO for PR-06; new violations fail CI. Six intentional `print()` calls annotated inline with `# lint: allow-print`. |
| PR-05 | deferred | Bugbot dashboard action that blocks merge on open `High`/`Medium` threads — skipped per maintainer call; unresolved threads will remain a per-PR review obligation rather than a CI gate. |

### Phase 2 — Structural refactors

Ordered by scope (small → large) and dependency. Each PR ships an ADR.

| PR | Status | Target |
|---|---|---|
| PR-06 | merged | `MigrationType` unification — see ADR-0006 |
| PR-07 | merged | Dialect capabilities matrix — see ADR-0007 |
| PR-08 | merged | `CommandOutput` abstraction — new `cli/_output.py` unifies the `is_machine_format` routing decision (was duplicated in `cli/main.py` and `cli/_command_handlers.py`). Banner in machine mode routed to **stderr** instead of suppressed (partially supersedes ADR-0005). 23 unit tests; 1194 passed in regression. ConsoleLog stderr routing deferred. |
| PR-09 | merged | Argparse parent parsers — extract 4 `parents=[_history, _strict, _filter, _target_version]` from the imperative `for subparser in [...]` loops. BUG-01/02/05 pattern already fixed by `bb47769` + enforced by PR-03's 210-case test; this PR is the "belt" refactor that makes the shape visible. Scope narrowed from the full declarative spec (deferred) — see ADR-0009. 470 CLI unit tests pass. |
| PR-10 | merged | `Migration._sql_statements` cache immutability — `parse_sql_statements(content_override=...)` no longer writes to the canonical cache. Closes Bugbot PR 160 line 386 at the source (not just at the flagged line). 9 contract tests + full migration suite (779/780). See ADR-0010. |
| PR-11 | merged | `_run_preflight()` helper centralises the `connect → create_history → populate` sequence. Fixes the Bugbot-flagged order bug in `info_command` (populate was called before connect). Adopted by `info_command` and `migrate_command`; `clean` keeps its bespoke error policy. 4 ordering contract tests + full migration suite (783/784). Full CommandLifecycle with hooks deferred — see ADR-0011. |

### Phase 3 — DD-ready artefacts

| PR | Status | Target |
|---|---|---|
| PR-12 | merged | `ARCHITECTURE.md` rewritten as a 340-line DD-facing overview (~30 min read). Previous 2717-line document preserved at `docs/architecture/detailed-architecture.md`. Links to stabilization plan, ADR index, existing per-subsystem docs (licensing, database-providers, sql-parsing, configuration, migration-engine). Honest "Known-deferred work" ledger at the end. |
| PR-13 | merged | `SECURITY.md` (174 lines) with disclosure process, supported versions, threat model (assets/adversaries/attack surface), secrets handling, supply chain, known limitations (JDBC provenance, license as commercial vs security control), defensive architecture cross-ref to tests. |
| PR-14 | merged (`af12328f`) | Public-API surface frozen: `api/py.typed` shipped (PEP 561), `docs/semver-policy.md` (136 lines) formalising public vs internal modules, PATCH/MINOR/MAJOR rules, one-minor-release deprecation overlap and release-time enforcement, plus `tests/unit/api/test_public_api_surface.py` (14 contract tests) pinning the surface in CI. |
| PR-15 | merged (`0cd6cfd3`) | `pytest-benchmark` baseline for the CPU-bound hot paths (checksum, filename parsing, placeholder substitution, `MigrationType` helpers, dialect-capability lookup, SQL statement splitting). Committed `tests/benchmarks/baseline.json` is an audit artefact, not a blocking gate — shared-runner ±30 % variance makes a fixed threshold either flappy or useless. New `benchmarks.yml` workflow runs on manual dispatch and uploads a JSON artefact for offline comparison. |

### Phase Oracle

`core/sql_parser/oracle/oracle_parser.py` is 1 402 lines and accounts
for 16 of 41 fixes since v1.1.0. Functional decomposition into five
focused modules behind a thin `OracleParser` facade — see
[ADR-0012](adr/0012-oracle-parser-split.md). Conformance-first: the
shared fixture harness must stay green through every extraction.

| PR | Status | Target |
|---|---|---|
| Phase-Oracle-01 | merged | Scoping scaffold — ADR-0012, 12 conformance fixtures (24 contract assertions) in `tests/unit/core/sql_parser/oracle/test_oracle_parser_conformance.py`, five empty skeleton modules in `core/sql_parser/oracle/`, no logic moved. 29/29 conformance + 90/90 full Oracle suite green. |
| Phase-Oracle-02 | merged | `_comments.py` (57 lines) with `strip_comments` + `strip_sql_comments` pure functions. Two private methods deleted from `oracle_parser.py` (1402 → 1379 lines). 16 new direct unit tests + 29 conformance assertions + 61 legacy Oracle tests — 106/106 green. |
| Phase-Oracle-03 | merged | `_sqlplus.py` (91 lines) with pure `is_sqlplus_command` — 27 directive patterns compiled at module load. Dead method deleted from `oracle_parser.py` (1379 → 1310 lines). Known divergence with `oracle_statement_parser.py::_is_sqlplus_command` (tokenizer path, 30 prefix-match commands) documented in the module; unification scheduled as a post-split cleanup. 52 new parametrised unit tests; full Oracle suite 158/158. |
| Phase-Oracle-04 | merged | `_object_extractor.py` (184 lines) with pure `extract_objects(sql, default_schema)` — table / view / sequence / procedure / index regexes compiled once at module load, repetitive per-kind loops deduplicated via `(pattern, class)` iteration. Method + five now-dead `core.sql_model` imports deleted from `oracle_parser.py` (1310 → 1114 lines). Known quirks (`GLOBAL TEMPORARY TABLE` name not extracted, `NOFORCE VIEW` name not extracted, `FUNCTION` classified as `PROCEDURE`, default-schema silently dropped on unqualified names) preserved byte-identical and documented in the module docstring; fixes scheduled as post-split work. 25 new direct unit tests + 29 conformance assertions + legacy Oracle suite — 164/164 green. |
| Phase-Oracle-05 | merged | `_statement_splitter.py` (233 lines) — pure module functions for the hot path: `split_statements_regex`, `extract_next_complete_statement`, `extract_regular_statement`, `is_plsql_keyword_start`, `is_empty_or_comment`, `word_at_position`. The PL/SQL block extractor is passed in via keyword argument until Phase-Oracle-06 extracts it (at which point the injection becomes a direct import). `_PLSQL_START_REGEX` compiled once at module load. Five methods + two class constants deleted from `oracle_parser.py` (1114 → 939 lines); 20 call sites of `self._word_at_position` rewritten. 66 new direct unit tests + 29 conformance assertions + legacy Oracle suite — 230/230 green. |
| Phase-Oracle-06 | merged | `_plsql_block.py` (675 lines) — pure module functions for the PL/SQL state machine: `extract_plsql_block`, `extract_java_source_block`, `parse_plsql_create_header`, `scan_to_plsql_body_start`, `handle_plsql_end_keyword`, `is_line_start_slash`, `is_single_plsql_block`, `is_partial_plsql_fragment`. All regexes pre-compiled; the `_statement_splitter` injection is replaced by a direct import (PR-05 keyword argument retired at call sites). Seven methods + four class constants + `_CASE_END_SQL_KEYWORDS` frozenset deleted from `oracle_parser.py` (939 → 310 lines). Legacy quirk documented and pinned: `handle_plsql_end_keyword` mutates a local `statement` string that does not propagate, so the literal "END" in `END IF / END LOOP / END CASE` is dropped from the emitted statement — preserved byte-identical; fix scheduled as post-split. 53 new direct unit tests + 29 conformance assertions + legacy Oracle suite — 283/283 green. |
| Phase-Oracle-07 | merged | Facade trim: the unused `_is_plsql_block` wrapper is deleted and `_is_partial_plsql_fragment` is inlined at its single `validate_sql` call site. `oracle_parser.py` drops 310 → 298 lines. ADR-0012 flipped to `Status: Done` with a Results section summarising per-PR deltas, pinned quirks, and post-split follow-ups. No code paths or tests change; 277/277 Oracle suite green. |

Each PR ends with a file-size gate: `oracle_parser.py` line count must
strictly decrease. Pure-function extracted modules must stay ≤ 300 lines;
`_plsql_block.py` is the single exception (sized at 675 lines) because
the PL/SQL state machine is ~450 lines of deeply coupled control flow
that cannot be split further without breaking the byte-identical
guarantee. Restructuring is a post-split task with its own regression
tests.

## Metrics and targets

| Metric | Today | Target |
|---|---|---|
| Line coverage | 77 % | ≥ 85 % by end of Phase 3 |
| `.flake8` ignore rules | 8 | ≤ 5 by end of Phase 2 (black-compat only) |
| Mypy strict flags enabled | 6 / 14 | 14 / 14 on new code by end of Phase 2 |
| Max file size (source) | 1402 → 675 (`_plsql_block.py`) | ≤ 500 by end of Phase Oracle; exceeded on `_plsql_block.py` by design (see row below) |
| Fix ratio (rolling 3 months) | ~44 % | < 15 % steady state |
| Bugbot unresolved High/Medium | tracked | 0 on merge |
| Bandit HIGH findings | 0 | 0 (blocking) |
| Bandit MEDIUM findings | 96 (B608 SQL-as-string) | baseline; silenced case-by-case |
| pip-audit known CVEs | 17 across 5 deps | 0 by end of Phase 0 (see below) |
| Xenon complexity ratchet | `F/F/F` (absolute/modules/average) | `C/B/B` end of Phase 2, `B/A/A` end of Oracle split |

## Known dependency CVEs

Surfaced by `pip-audit` during PR-0E baseline run (2026-04-19) and
resolved in PR-0G by bumping version floors in `pyproject.toml`. See
also ADR-0003 on the Python 3.8 drop this required.

| Package | Prior floor | New floor | CVEs closed |
|---|---|---|---|
| `cryptography` | `>=41.0.0` | `>=46.0.6` | PYSEC-2024-225, CVE-2023-50782, CVE-2024-0727, GHSA-h4gh-qq45-vh27, CVE-2026-26007, CVE-2026-34073 |
| `PyJWT` | `>=2.8.0` | `>=2.12.0` | CVE-2026-32597 |
| `setuptools` | (build-only, `>=42`) | `>=78.1.1` | PYSEC-2025-49 (×2), CVE-2024-6345 |
| `wheel` | (build-only, unpinned) | `>=0.46.2` | CVE-2026-24049 |
| `pip` | user's pip | — | CVE-2025-8869, CVE-2026-1703 are tied to the user's local `pip` version, not pinnable by the project. Documented in README install guide. |

## Governance

- Squash-merge only. Branches protected on `main` and `develop`.
- Every PR uses the template and follows Conventional Commits.
- Every structural PR ships an ADR in `docs/adr/`.
- Deviations from this plan require a new ADR superseding it.
