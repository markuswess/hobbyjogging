#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./dashboard.sh [dashboard options] [--no-open]

Generates the static HTML dashboard and opens its index page in the browser.
All options other than --no-open are passed to the dashboard command:

  --output DIR       write the site to DIR (default: $HOBBYJOGGING_DASHBOARD_DIR/dashboard)
  --days N           overview window in days (default 14)
  --activities N     number of recent activity pages (default 50)
  --chart-days N     main chart history in days (default 182)
  --future-days N    main chart planned horizon in days (default 14)
  --reports LIST     comma-separated Markdown reports to embed
                     (overview,daily,weekly,monthly,yearly,report,planned,
                     subt-report,compare-years,compare-months)
  --source database|intervals
  --include-review

Examples:
  ./dashboard.sh
  ./dashboard.sh --days 30 --activities 100
  ./dashboard.sh --reports overview,daily,planned
  ./dashboard.sh --no-open

Environment:
  HOBBYJOGGING_DASHBOARD_DIR   parent directory for the default dashboard
  BROWSER                      browser command to use instead of xdg-open
  NO_OPEN=1                    do not open the browser
EOF
}

open_page=1
args=()

for arg in "$@"; do
    case "$arg" in
        --no-open)
            open_page=0
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            args+=("$arg")
            ;;
    esac
done

if [[ "${NO_OPEN:-0}" == "1" ]]; then
    open_page=0
fi

site="$(uv run --env-file .env python -m hobbyjogging_report dashboard "${args[@]}")"
echo "$site"

if (( open_page == 0 )); then
    exit 0
fi

if [[ "$site" = /* ]]; then
    page="$site/index.html"
else
    page="$ROOT/$site/index.html"
fi

if [[ -n "${BROWSER:-}" ]]; then
    "$BROWSER" "$page" >/dev/null 2>&1 &
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$page" >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
    open "$page" >/dev/null 2>&1 &
else
    echo "warning: no browser opener found; open $page" >&2
fi
