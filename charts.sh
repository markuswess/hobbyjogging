#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./charts.sh [chart|subt-chart|subt-hr-chart] [args...]
  ./charts.sh --source database|intervals [mode] [args...]

With no mode, builds the weekly distance chart. The output file path is
printed. The database source is the default.

Examples:
  ./charts.sh
  ./charts.sh chart chart.png
  ./charts.sh chart --days 90
  ./charts.sh subt-chart --days 365
  ./charts.sh subt-chart --output subt.png
  ./charts.sh subt-hr-chart --from 2026-01-01 --to 2026-06-30 --output hr.png
  ./charts.sh subt-chart --source intervals

Charts accept the same --days / --from / --to / --output options as the
direct CLI.
EOF
}

args=("$@")
mode="chart"
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
    chart|subt-chart|subt-hr-chart)
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
