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
After a successful sync it regenerates the static dashboard. The sync summary
reports what changed and exits non-zero if a source failed.

Options:
  --days N          activity/wellness/Garmin lookback (default 30)
  --since DATE      explicit start date (overrides --days)
  --plan-days N     planned-event horizon (default 182)
  --no-garmin       skip the Garmin fetch
  --no-intervals    skip the Intervals.icu import
  --no-fit          skip the FIT archive scan
  --no-scan         skip the quality review scan
  --no-dashboard    skip dashboard regeneration
  --full            re-import every FIT file (ignore the known-path skip)
  --database PATH   use a database other than HOBBYJOGGING_DB

Examples:
  ./sync.sh
  ./sync.sh --days 14
  ./sync.sh --since 2026-10-01
  ./sync.sh --no-garmin
  ./sync.sh --no-scan --full
  ./sync.sh --no-dashboard

The dashboard is written to $HOBBYJOGGING_DASHBOARD_DIR/dashboard when that
variable is set, or to data/dashboard otherwise.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

args=("$@")
sync_args=()
database=""
generate_dashboard=1
index=0

while (( index < ${#args[@]} )); do
    case "${args[$index]}" in
        --no-dashboard)
            generate_dashboard=0
            index=$((index + 1))
            ;;
        --database)
            database="${args[$((index + 1))]:-}"
            sync_args+=("${args[$index]}")
            if (( index + 1 < ${#args[@]} )); then
                sync_args+=("${args[$((index + 1))]}")
            fi
            index=$((index + 2))
            ;;
        --database=*)
            database="${args[$index]#--database=}"
            sync_args+=("${args[$index]}")
            index=$((index + 1))
            ;;
        *)
            sync_args+=("${args[$index]}")
            index=$((index + 1))
            ;;
    esac
done

uv run --env-file .env hobbyjogging-import sync "${sync_args[@]}"

if (( generate_dashboard )); then
    if [[ -n "$database" ]]; then
        HOBBYJOGGING_DB="$database" \
            uv run --env-file .env python -m hobbyjogging_report dashboard
    else
        uv run --env-file .env python -m hobbyjogging_report dashboard
    fi
fi
