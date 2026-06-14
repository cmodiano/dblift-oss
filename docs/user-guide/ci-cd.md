# Running dblift in CI/CD

dblift is a pip package with no system dependencies, so CI is just
`pip install` + a dblift command. These recipes use OSS commands only
(`validate`, `info`). `validate-sql`, `drift`, and `plan` ship in
`dblift-enterprise`.

All commands need a reachable database. Below, the DB connection is supplied
via the `DBLIFT_DB_URL` environment variable (overrides `dblift.yaml`).

## GitHub Actions

```yaml
name: dblift
on:
  pull_request:
    paths: ["migrations/**"]

jobs:
  validate:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: dblift
          POSTGRES_PASSWORD: dblift
          POSTGRES_DB: dblift
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    env:
      DBLIFT_DB_URL: postgresql+psycopg://dblift:dblift@localhost:5432/dblift
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install "dblift[postgresql]"
      - run: dblift migrate   # apply to the ephemeral CI database
      - run: dblift validate  # checksums / order / applied-state integrity
      - run: dblift info      # report pending migrations
```

## GitLab CI

```yaml
stages: [validate]

validate-migrations:
  stage: validate
  image: python:3.11
  services:
    - name: postgres:16
      alias: postgres
  variables:
    POSTGRES_USER: dblift
    POSTGRES_PASSWORD: dblift
    POSTGRES_DB: dblift
    DBLIFT_DB_URL: "postgresql+psycopg://dblift:dblift@postgres:5432/dblift"
  rules:
    - changes: [migrations/**/*]
  script:
    - pip install "dblift[postgresql]"
    - dblift migrate
    - dblift validate
    - dblift info
```

## Pre-commit (local)

```yaml
repos:
  - repo: https://github.com/cmodiano/dblift-oss
    rev: v1.8.0   # pin to a released tag
    hooks:
      - id: dblift-validate
      - id: dblift-info
```

The hooks need a configured `dblift.yaml` (or `DBLIFT_DB_URL`) and a reachable
database — typically the local dev DB from your `docker-compose.yml`. dblift has
no offline (database-free) lint in OSS.
