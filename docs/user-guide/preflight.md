# Deployment Preflight

`dblift preflight` runs deployment-readiness checks before a migration reaches a
DBA review or deployment job. It combines the offline snapshot plan, SQL
validation rules, optional Docker target provisioning, and migration replay in
one report.

`preflight` does not replace `plan` or `validate-sql`; it reuses their finding
model in a broader release-readiness workflow:

- `plan` predicts pending work from a committed snapshot without a database.
- `validate-sql` validates SQL files without a database.
- `validate-sql` remains the primary offline SQL policy gate and source of SQL
  policy evidence.
- `preflight` orchestrates the full deployment-readiness workflow.

The snapshot is the environment contract. It carries the migration state,
checksums for applied versioned and repeatable migrations, and the schema/object
model produced by the snapshot extraction options. A pending migration means
"absent from this snapshot", not necessarily "introduced by this PR".

## Environment Branch Workflow

One branch can represent one environment. The branch stores the snapshot that
represents the current environment state:

```text
.dblift/environments/uat.snapshot.json
```

When a PR adds migrations for that environment branch, run:

```bash
dblift preflight \
  --snapshot-model .dblift/environments/uat.snapshot.json \
  --container-image artifactory.company/db/oracle-uat-validation:latest \
  --replay-scope all \
  --container-port 15210:1521 \
  --db-url "oracle+oracledb://localhost:15210?service_name=XEPDB1" \
  --format html \
  --output dblift-preflight.html \
  --fail-on error
```

The default `--replay-scope all` assumes the container starts empty. DBLift runs
`migrate` against the validation container, so historical scripts create the
dependencies required by the new scripts. The snapshot is still used to identify
the deployment delta that reviewers care about.

## Report Artifacts

Keep CI output focused on the job system when you only need annotations:

```bash
dblift preflight \
  --snapshot-model .dblift/environments/uat.snapshot.json \
  --container-existing validation-db \
  --replay-scope all \
  --db-url "postgresql+psycopg://localhost:15432/app" \
  --format github-actions \
  --fail-on error
```

For DBA, release, or change-advisory review, publish the enriched reports as CI
artifacts. `--format` accepts multiple comma-separated formats. When more than
one format is requested, use `--output-dir`:

```bash
dblift preflight \
  --snapshot-model .dblift/environments/uat.snapshot.json \
  --container-existing validation-db \
  --replay-scope all \
  --db-url "postgresql+psycopg://localhost:15432/app" \
  --format json,html,text \
  --output-dir dblift-reports \
  --fail-on error
```

DBLift writes one timestamped file per format using the same report timestamp:

```text
dblift-reports/preflight-report-20260601T143522Z.json
dblift-reports/preflight-report-20260601T143522Z.html
dblift-reports/preflight-report-20260601T143522Z.txt
```

Use `json` for CI ingestion or artifact indexing, `html` for the enriched
offline report, and `text` for release logs or long-term evidence bundles.

If another branch deployed to the environment, make sure the CI job uses the
latest snapshot from the environment branch. Without live target database access,
`preflight` cannot know that a committed snapshot is stale; it can only evaluate
the snapshot it was given.

Use `--replay-scope planned` only when the container image is already preloaded
with DBLift history matching the snapshot:

```bash
dblift preflight \
  --snapshot-model .dblift/environments/uat.snapshot.json \
  --container-image artifactory.company/db/uat-snapshot-loaded:latest \
  --replay-scope planned \
  --db-url "postgresql+psycopg://localhost:15432/app"
```

## Existing Container

If CI already starts the database container:

```bash
dblift preflight \
  --snapshot-model .dblift/environments/uat.snapshot.json \
  --container-existing validation-db \
  --replay-scope all \
  --db-url "postgresql+psycopg://localhost:15432/app" \
  --format github-actions \
  --fail-on error
```

## Offline-Only Mode

Use `--skip-replay` when container replay is handled by another job:

```bash
dblift preflight \
  --snapshot-model .dblift/environments/uat.snapshot.json \
  --skip-replay \
  --format json
```
