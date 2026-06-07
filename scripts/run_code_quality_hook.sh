#!/usr/bin/env bash
# Used by pre-commit: prefer project venv so black/isort/flake8/mypy resolve without manual activate.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${ROOT}" ]]; then
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
cd "${ROOT}"
if [[ -x "${ROOT}/venv/bin/python" ]]; then
  PATH="${ROOT}/venv/bin:${PATH}"
  export PATH
fi
exec bash "${ROOT}/scripts/check_code_quality.sh"
