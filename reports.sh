#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./reports.sh [daily|weekly|monthly|yearly|all|report|session|classify] [args...]

With no mode, builds the full daily + weekly + monthly + yearly report.
The generated Markdown is copied to the clipboard with wl-copy.

Examples:
  ./reports.sh
  ./reports.sh weekly
  ./reports.sh report --days 90
  ./reports.sh report --from 2026-01-01 --to 2026-03-31
  ./reports.sh session 2026-10-22

Environment:
  NO_COPY=1    do not copy to the clipboard
  NO_COLOR=1   disable ANSI colours
  NO_PRETTY=1  print the raw Markdown instead of the terminal rendering
EOF
}

mode="${1:-all}"

case "$mode" in
    -h|--help)
        usage
        exit 0
        ;;
    daily|weekly|monthly|yearly|all|report|session|classify)
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

args=("$@")

if (( ${#args[@]} == 0 )); then
    args=(daily)
fi

tmp="$(mktemp "${TMPDIR:-/tmp}/intervals-report.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

if ! uv run --env-file .env python -m intervals_report "${args[@]}" >"$tmp"; then
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

    "$python_bin" -m intervals_report.mdpretty <"$tmp"
else
    cat "$tmp"
fi
