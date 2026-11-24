#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# The notebook lives outside the public repo. Default to the shipped bench so a
# fresh clone still works; fail clearly when an explicit path is missing.
LAB_DIR="${HOBBYJOGGING_LAB_DIR:-$ROOT/experiments}"
if [[ ! -d "$LAB_DIR" ]]; then
    echo "error: lab directory not found: $LAB_DIR" >&2
    echo "set HOBBYJOGGING_LAB_DIR to your lab notebook directory" >&2
    exit 1
fi
export HOBBYJOGGING_LAB_DIR

# The lab is interactive, so unlike reports.sh it must not capture stdout.
env_args=()
if [[ -f .env ]]; then
    env_args=(--env-file .env)
fi
exec uv run "${env_args[@]}" python -m hobbyjogging_report.shell "$@"
