#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./charts.sh [volume|subt-pace|subt-hr] [args...]
  ./charts.sh --source database|intervals [mode] [args...]

With no mode, builds the weekly volume chart. The output file path is
printed. The database source is the default.

Examples:
  ./charts.sh
  ./charts.sh volume
  ./charts.sh volume --days 90
  ./charts.sh volume --output volume.png
  ./charts.sh subt-pace --days 365
  ./charts.sh subt-pace --output subt.png
  ./charts.sh subt-hr --from 2026-01-01 --to 2026-06-30 --output hr.png
  ./charts.sh subt-pace --source intervals

Charts accept the same --days / --from / --to / --output options as the
direct CLI.
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
    volume|subt-pace|subt-hr)
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
