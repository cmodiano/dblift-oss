# Benchmark suite

`pytest-benchmark` baselines for the CPU-bound hot paths and one
SQLite end-to-end migration. **Not run on every PR** — CI runner CPU
share is too variable to produce meaningful p50/p95 comparisons.
They run on manual dispatch via `.github/workflows/benchmarks.yml`
or locally.

## What's covered

| File | Path under benchmark | Why |
|---|---|---|
| `test_bench_checksum.py` | `calculate_migration_script_checksum` | CRC32 per-line on migration content. Called on every Migration load and every history write. |
| `test_bench_filename_parsing.py` | `MigrationScriptManager.parse_filename` | Regex-heavy; runs once per migration file on every `info`, `migrate`, `validate`. |
| `test_bench_placeholder_substitution.py` | `PlaceholderService.replace_placeholders` | Pre-tokenisation substitution; hot path for migration execution. |
| `test_bench_sql_statement_splitting.py` | `Migration.parse_sql_statements` (SQLite + PostgreSQL dialects) | Tokeniser dispatch + object extraction. The single largest CPU cost of a migration run. |
| `test_bench_type_match_helpers.py` | `is_versioned`, `is_migration_type`, `migration_type_name` | Called per-migration in the display-state classifier; millions of calls at scale. |
| `test_bench_dialect_capabilities.py` | `get_dialect_capabilities` | Hot lookup; called per-command and per-phase. |
| `test_bench_sqlite_migrate_end_to_end.py` | `dblift migrate` on SQLite via in-process `DBLiftClient` | Whole-system baseline; reveals regressions the per-function benchmarks miss. |

## Running

### Locally

```bash
# Full suite; writes to .benchmarks/
pytest tests/benchmarks/ --benchmark-only

# With JSON output (for CI artefact / manual comparison)
pytest tests/benchmarks/ --benchmark-only \
    --benchmark-json=benchmarks.json

# Compare against a committed baseline (see below)
pytest tests/benchmarks/ --benchmark-only \
    --benchmark-compare=tests/benchmarks/baseline.json \
    --benchmark-compare-fail=mean:200%
```

### CI (manual dispatch)

```
.github/workflows/benchmarks.yml
```

Triggered via *Actions → Benchmarks → Run workflow*. Produces a JSON
artefact you can download and feed to `pytest-benchmark compare`.

## Why no automatic regression gate

GitHub Actions runners share CPUs with noisy neighbours. Benchmark
numbers drift ±30% between runs on identical code. A fixed threshold
either:

- Fails often on noise (false positives erode trust in CI).
- Is loose enough (e.g. `--benchmark-compare-fail=mean:500%`) that it
  only catches catastrophic regressions, which the end-to-end test
  already surfaces another way.

The current policy is:

1. Maintainer runs the suite locally before any PR that touches a hot
   path (parser, placeholder service, type-match helpers).
2. CI runs benchmarks on manual dispatch when performance-relevant
   changes land.
3. The committed `baseline.json` represents "on reference hardware,
   these are the expected numbers" — an audit artefact, not a CI gate.

Upgrading to a dedicated perf runner (bare metal, pinned CPUs) would
change this. Not on the current roadmap.

## Updating the baseline

After a legitimate perf change (hot-path refactor, new Python minor,
dep bump that shifts CPython behaviour):

```bash
pytest tests/benchmarks/ --benchmark-only \
    --benchmark-json=tests/benchmarks/baseline.json
git add tests/benchmarks/baseline.json
# Commit with an explanation of why numbers moved.
```

## Reference hardware

The committed `baseline.json` was generated on:

- CPU: Intel Core i7-12700H (generic CI-class laptop)
- Python: 3.11.15 on Linux 6.5
- Run with `pytest-benchmark>=4.0.0`
- `pip install -e ".[dev]"` environment

If your local numbers differ by more than ~30% from the baseline, that
is most likely hardware variance, not a regression. Re-run on similar
hardware before raising a concern.
