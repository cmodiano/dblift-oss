#!/usr/bin/env bash
# Reproduce CI integration runs locally (mirrors .github/workflows/integration-tests-new.yml).
#
# Usage:
#   ./scripts/run_integration_local.sh postgresql
#   ./scripts/run_integration_local.sh sqlserver --maxfail=1
#
# Env:
#   INTEGRATION_PYTEST_PATH  Default: tests/integration/commands/
#   INTEGRATION_WAIT_MULT    Multiply health-wait attempts (default 1); use 2 for slow DB2 pulls

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${1:?usage: run_integration_local.sh <postgresql|mysql|sqlserver|db2|oracle|cosmosdb> [pytest args...]}"
shift || true

PY_PATH="${INTEGRATION_PYTEST_PATH:-tests/integration/commands/}"
WAIT_MULT="${INTEGRATION_WAIT_MULT:-1}"
max_attempts=$((60 * WAIT_MULT))

cd "$ROOT/tests/integration"
echo "Starting: docker compose up -d $SERVICE"
docker compose up -d "$SERVICE"

attempt=1
while [ "$attempt" -le "$max_attempts" ]; do
  if docker compose ps "$SERVICE" 2>/dev/null | grep -q "healthy"; then
    echo "OK: $SERVICE is healthy"
    break
  fi
  echo "Waiting for $SERVICE healthy ($attempt/$max_attempts)..."
  sleep 10
  attempt=$((attempt + 1))
done

if [ "$attempt" -gt "$max_attempts" ]; then
  echo "Timeout waiting for healthy: $SERVICE"
  docker compose logs --tail 200 "$SERVICE" || true
  exit 1
fi

echo "Extra settle time (30s)..."
sleep 30

cd "$ROOT"
export DBLIFT_CORE_TEST_DB="$SERVICE"
echo "DBLIFT_CORE_TEST_DB=$SERVICE  pytest $PY_PATH"
exec python -m pytest "$PY_PATH" -v --tb=short "$@"
