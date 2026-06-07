#!/bin/bash
# This script runs mypy on the core modules
set -e
cd "$(dirname "$0")"
echo "Running mypy type checking..."
for pkg in cli config core db; do
    echo "Type checking $pkg..."
    mypy --config-file pyproject.toml "$pkg"
done
