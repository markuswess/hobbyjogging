#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./doctor.sh [--no-network] [--database PATH] [--sources PATH]

Checks the installation and prints the next command: paths and permissions,
schema version, configured sources and credentials, a bounded API liveness
probe (skip it with --no-network), pending backfills and source freshness.
Exits non-zero when a check fails.

Options:
  --no-network        skip the Garmin/Intervals/Runalyze probes
  --timeout SECONDS   per-probe timeout (default: 10)
  --database PATH     check another database
  --sources PATH      check another sources.toml
  --fit-dir PATH      check another FIT archive
  --strava-dir PATH   check another Strava drop directory
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

uv run "${env_args[@]}" python -m hobbyjogging_maintenance doctor "$@"
