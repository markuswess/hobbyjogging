#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./charts.sh [volume|subt-pace|subt-hr|load|time|recovery] [args...]
  ./charts.sh --source database|intervals [mode] [args...]

With no mode, builds the weekly volume chart. The output file path is
printed. The database source is the default.

Examples:
  ./charts.sh
  ./charts.sh volume
  ./charts.sh volume --days 90
  ./charts.sh volume --output volume.png
  ./charts.sh volume --planned-days 0
  ./charts.sh subt-pace --days 365
  ./charts.sh subt-pace --output subt.png
  ./charts.sh subt-hr --from 2026-01-01 --to 2026-06-30 --output hr.png
  ./charts.sh load --days 180
  ./charts.sh load --base-days 182 --fitness-days 42 --fatigue-days 7
  ./charts.sh time --days 90
  ./charts.sh time --zones 4 --zone-window base
  ./charts.sh recovery --days 90
  ./charts.sh subt-pace --source intervals

Charts accept the same --days / --from / --to / --output options as the
direct CLI. The volume, load, time, and recovery charts include planned
workouts and accept --planned-days N (default 28, ignored with --to; 0
disables the future extension). The load, volume, and time charts also
accept --base-days / --fitness-days / --fatigue-days. The time chart also
accepts --zones and --zone-window base|fitness|fatigue. The recovery chart
accepts --window.
EOF
}

args=("$@")
mode="volume"
explicit_mode=0
index=0

while (( index < ${#args[@]} )); do
    case "${args[$index]}" in
        --source)
            index=$((index + 2))
            ;;
        --source=*|--include-review)
            index=$((index + 1))
            ;;
        *)
            mode="${args[$index]}"
            explicit_mode=1
            break
            ;;
    esac
done

case "$mode" in
    -h|--help)
        usage
        exit 0
        ;;
    volume|subt-pace|subt-hr|load|time|recovery)
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

if (( explicit_mode == 0 )); then
    args=("$mode" "${args[@]}")
fi

uv run --env-file .env python -m hobbyjogging_report "${args[@]}"
