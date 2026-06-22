#!/usr/bin/env bash

set -e
set -x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_DIR="$(cd "${BACKEND_DIR}/.." && pwd)"
TEST_DIR="${PROJECT_DIR}/tests"

cd "${BACKEND_DIR}"

if python -m coverage --version >/dev/null 2>&1; then
  python -m coverage run --source="${BACKEND_DIR}" -m pytest "${TEST_DIR}" "$@"
  python -m coverage report --show-missing
  python -m coverage html --title "${*:-coverage}"
else
  python -m pytest "${TEST_DIR}" "$@"
fi
