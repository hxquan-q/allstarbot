#! /usr/bin/env bash
set -e
set -x

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${BACKEND_DIR}"

if [ -f "tests_pre_start.py" ]; then
  python tests_pre_start.py
fi

bash scripts/test.sh "$@"
