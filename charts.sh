#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./charts.sh [overview|volume|subt|vo2max|load|time|recovery] [args...]
  ./charts.sh --source database|intervals [mode] [args...]

With no mode, builds the weekly volume chart. The output file path is
printed. The database source is the default.

Examples:
  ./charts.sh
  ./charts.sh overview
  ./charts.sh overview --chart-days 90 --future-days 21
  ./charts.sh volume
  ./charts.sh volume --days 90
  ./charts.sh volume --output volume.png
  ./charts.sh volume --planned-days 0
  ./charts.sh subt --days 365
  ./charts.sh subt --output subt.png
  ./charts.sh subt --from 2026-01-01 --to 2026-06-30 --output subt.png
  ./charts.sh vo2max --days 365
  ./charts.sh load --days 180
  ./charts.sh load --base-days 182 --fitness-days 42 --fatigue-days 7
  ./charts.sh time --days 90
  ./charts.sh time --zones 4 --zone-window base
  ./charts.sh recovery --days 90
  ./charts.sh subt --source intervals

Charts accept the same --days / --from / --to / --output options as the
direct CLI. The overview chart uses --chart-days (default 182) and
--future-days (default 14), and writes overview.png by default; it also
draws the Garmin VO2max standing value on a second axis. The volume,
load, time, and recovery charts include planned workouts and accept
--planned-days N (default 28, ignored with --to; 0 disables the future
extension). Their average lines continue through the planned days as dashed
projections. The load, volume, and time charts also accept --base-days /
--fitness-days / --fatigue-days. The time chart also accepts --zones and
--zone-window base|fitness|fatigue. The recovery chart accepts --window.
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
            mode_index=$index
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
    volume|overview|subt|vo2max|load|time|recovery)
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac

chart_mode="$mode"
if [[ "$mode" == "overview" ]]; then
    chart_mode="overview-chart"
fi

if (( explicit_mode == 0 )); then
    args=("$chart_mode" "${args[@]}")
else
    args[$mode_index]="$chart_mode"
fi

uv run --env-file .env python -m hobbyjogging_report "${args[@]}"
