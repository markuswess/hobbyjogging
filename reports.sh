#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./reports.sh [daily|overview|weekly|monthly|yearly|all|report|compare|subt-report|planned|session|classify|activities] [args...]
  ./reports.sh --source database|intervals [mode] [args...]

With no mode, builds the daily report. The generated Markdown is copied to
the clipboard with wl-copy. The database source is the default.
For charts, use ./charts.sh. For the dashboard, use ./dashboard.sh.

Examples:
  ./reports.sh
  ./reports.sh weekly
  ./reports.sh overview
  ./reports.sh overview --future-days 21
  ./reports.sh report --days 90
  ./reports.sh report --from 2026-01-01 --to 2026-03-31
  ./reports.sh compare years
  ./reports.sh compare months
  ./reports.sh compare months --from 2025-01-01 --to 2025-12-31
  ./reports.sh subt-report --days 90
  ./reports.sh planned
  ./reports.sh planned --days 56
  ./reports.sh activities
  ./reports.sh activities --limit 50 --add id,category
  ./reports.sh session
  ./reports.sh session last
  ./reports.sh session 2026-10-22
  ./reports.sh session <activity-id>
  ./reports.sh weekly --source intervals

Environment:
  NO_COPY=1    do not copy to the clipboard
  NO_COLOR=1   disable ANSI colours
  NO_PRETTY=1  print the raw Markdown instead of the terminal rendering
EOF
}

args=("$@")
mode="daily"
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
    daily|overview|weekly|monthly|yearly|all|report|compare|subt-report|planned|session|classify|activities)
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

if (( explicit_mode == 0 )); then
    args=("$mode" "${args[@]}")
fi

tmp="$(mktemp "${TMPDIR:-/tmp}/hobbyjogging-report.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

if ! uv run --env-file .env python -m hobbyjogging_report "${args[@]}" >"$tmp"; then
    cat "$tmp" >&2
    exit 1
fi

if [[ "${NO_COPY:-0}" != "1" ]]; then
    if command -v wl-copy >/dev/null 2>&1; then
        if ! wl-copy <"$tmp"; then
            echo "warning: wl-copy failed; clipboard was not updated" >&2
        fi
    else
        echo "warning: wl-copy not found; clipboard was not updated" >&2
    fi
fi

if [[ -t 1 && "${NO_PRETTY:-0}" != "1" ]]; then
    python_bin="$ROOT/.venv/bin/python"

    if [[ ! -x "$python_bin" ]]; then
        python_bin="python3"
    fi

    "$python_bin" -m hobbyjogging_report.mdpretty <"$tmp"
else
    cat "$tmp"
fi
