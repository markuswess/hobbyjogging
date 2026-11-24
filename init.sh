#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./init.sh [--database PATH] [--fit-dir PATH]

Creates and migrates the training database and makes sure the FIT directory
exists. Safe to re-run: a second run only checks the schema. The database path
comes from --database, $HOBBYJOGGING_DB, or data/hobbyjogging.db.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

env_args=()
if [[ -f .env ]]; then
    env_args=(--env-file .env)
fi

uv run "${env_args[@]}" python -m hobbyjogging_maintenance init "$@"
