#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./sync.sh [options]

Runs the incremental sync: Garmin fetch, Intervals.icu import (activities,
wellness, planned events), FIT archive import, then the quality review scan.
The sync summary reports what changed and exits non-zero if a source failed.

Options:
  --days N          activity/wellness/Garmin lookback (default 30)
  --since DATE      explicit start date (overrides --days)
  --plan-days N     planned-event horizon (default 182)
  --no-garmin       skip the Garmin fetch
  --no-intervals    skip the Intervals.icu import
  --no-fit          skip the FIT archive scan
  --no-scan         skip the quality review scan
  --full            re-import every FIT file (ignore the known-path skip)
  --database PATH   use a database other than HOBBYJOGGING_DB

Examples:
  ./sync.sh
  ./sync.sh --days 14
  ./sync.sh --since 2026-10-01
  ./sync.sh --no-garmin
  ./sync.sh --no-scan --full
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

exec uv run --env-file .env hobbyjogging-import sync "$@"
