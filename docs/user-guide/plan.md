# Offline Migration Plans

`dblift plan` compares local migration scripts with a DBLift snapshot file. It
does not connect to the target database, create the history table, or execute
SQL. This makes it suitable for CI jobs where the database is not reachable.

```bash
dblift plan \
  --snapshot-model .dblift/environments/prod.snapshot.json \
  --format json \
  --fail-on error
```

The snapshot is the environment state. A plan reports:

- pending versioned migrations
- repeatable migrations whose checksum changed or that are missing from the snapshot
- checksum drift for already-applied versioned migrations when the snapshot contains checksums
- SQL validation results for planned SQL scripts

`--fail-on never|error|warning|info` controls the minimum finding severity that
returns a non-zero exit code. The default is `error`, so pending migrations are
reported as informational findings without failing CI, while checksum drift and
SQL validation errors fail.

## Validation Scope

By default, SQL validation runs only on pending versioned migrations and changed
repeatables:

```bash
dblift plan --snapshot-model prod.snapshot.json
```

Use `--validate-scope all` to validate every local versioned and repeatable SQL
migration:

```bash
dblift plan --snapshot-model prod.snapshot.json --validate-scope all
```

Use `--skip-validate-sql` when another job already performs SQL validation:

```bash
dblift plan --snapshot-model prod.snapshot.json --skip-validate-sql
```

## Environment Branch Example

One practical CI pattern is one branch per environment. Each environment branch
stores the snapshot produced after deployment.

```yaml
- name: Load prod snapshot
  run: |
    git fetch origin env/prod
    git show origin/env/prod:.dblift/environments/prod.snapshot.json > prod.snapshot.json

- name: Plan pending migrations
  run: |
    dblift plan \
      --snapshot-model prod.snapshot.json \
      --format github-actions \
      --fail-on error
```

Machine-readable CI formats are shared with `validate-sql`: `json`, `sarif`,
`github-actions`, `gitlab`, and `compact`. Use `html` for the full report and
`console` for human output.

## Report Artifacts

Use a CI-native format when the job needs annotations or a small parser-facing
payload:

```bash
dblift plan \
  --snapshot-model prod.snapshot.json \
  --format github-actions \
  --fail-on error
```

Use report artifacts when the result should be downloaded from CI and reviewed
offline. `--format` accepts multiple comma-separated formats. When more than one
format is requested, write them to an output directory:

```bash
dblift plan \
  --snapshot-model prod.snapshot.json \
  --format json,html,text \
  --output-dir dblift-reports \
  --fail-on error
```

DBLift writes one timestamped file per format using the same report timestamp:

```text
dblift-reports/plan-report-20260601T143522Z.json
dblift-reports/plan-report-20260601T143522Z.html
dblift-reports/plan-report-20260601T143522Z.txt
```

Use `json` for CI ingestion or artifact indexing, `html` for the enriched
human-readable report, and `text` for logs or release evidence that should stay
easy to diff.

| Finding | Severity |
|---|---|
| validate-sql syntax error | error |
| validate-sql rule error | error |
| validate-sql warning | warning |
| validate-sql info | info |
| plan checksum drift | error |
| plan SQL validation failure | error |
| plan pending migration | info |
| plan legacy or incomplete snapshot warning | warning |

Older snapshots that only contain `applied_versions` still work, but versioned
checksum drift checks are limited until a newer snapshot with the `applied`
manifest is committed.

## From Plan To Preflight

Use `dblift plan` when CI cannot reach a database and you only need the
snapshot-based deployment plan plus SQL validation.

Use `dblift preflight` when CI can start or reuse a validation database
container and you want DBLift to run the migration replay phase. Use
`--replay-scope all` for an empty container, or `--replay-scope planned` for a
container already loaded to the snapshot state.
