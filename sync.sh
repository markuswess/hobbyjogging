#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./sync.sh [options]

Runs the whole configured pipeline:

  fetch     Garmin, Intervals.icu, the FIT archive, Runalyze (budgeted) and
            the newest unimported Strava export
  derive    offline Runalyze gear and VO2max, and race results
  maintain  the idempotent recomputes (classification, thresholds, zones,
            periods, race links, canonical fields)
  scan      the quality review scan
  render    the static dashboard

A source that is disabled in sources.toml or has no credential is skipped with
a warning; a configured source that fails is reported and the rest still run.
The command exits non-zero only when a configured source fails.

Options:
  --days N           activity/wellness/Garmin lookback (default 30)
  --since DATE       explicit start date (overrides --days)
  --plan-days N      planned-event horizon (default 182)
  --no-garmin        skip the Garmin fetch
  --no-intervals     skip the Intervals.icu import
  --no-fit           skip the FIT archive scan
  --no-runalyze      skip Runalyze enrichment and derivations
  --no-strava        skip the Strava export
  --no-derive        skip the offline Runalyze derivations
  --no-maintenance   skip the maintenance recomputes
  --no-classify      alias for --no-maintenance
  --no-scan          skip the quality review scan
  --no-dashboard     skip dashboard regeneration
  --full             re-import every FIT file (ignore the known-path skip)
  --database PATH    use a database other than HOBBYJOGGING_DB

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

now_ms() {
    date +%s%3N
}

format_ms() {
    printf '%d.%03ds' $(( $1 / 1000 )) $(( $1 % 1000 ))
}

env_args=()
if [[ -f .env ]]; then
    env_args=(--env-file .env)
fi

args=("$@")
sync_args=()
database=""
generate_dashboard=1
generate_maintenance=1
generate_scan=1
maintenance_ms=0
scan_ms=0
dashboard_ms=0
index=0

while (( index < ${#args[@]} )); do
    case "${args[$index]}" in
        --no-dashboard)
            generate_dashboard=0
            index=$((index + 1))
            ;;
        --no-classify|--no-maintenance)
            generate_maintenance=0
            index=$((index + 1))
            ;;
        --no-scan)
            generate_scan=0
            sync_args+=("${args[$index]}")
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

# The import step scans too, but the maintenance recomputes below open and
# close their own review items. Let the shell run the scan once, afterwards,
# so the order is fetch -> derive -> maintain -> scan -> dashboard.
uv run "${env_args[@]}" hobbyjogging-import sync --no-scan "${sync_args[@]}"

database_args=()
if [[ -n "$database" ]]; then
    database_args=(--database "$database")
fi

if (( generate_maintenance )); then
    maintenance_started=$(now_ms)
    for task in \
        workout_sets_current \
        derived_intervals_current \
        workout_classification_queue \
        athlete_thresholds_current \
        activity_zone_configs_current \
        derived_zone_configs_current \
        training_periods_current \
        race_links_current \
        runalyze_load_current \
        recompute_canonical
    do
        uv run "${env_args[@]}" python -m hobbyjogging_maintenance \
            run "$task" "${database_args[@]}"
    done
    maintenance_ms=$(( $(now_ms) - maintenance_started ))
fi

if (( generate_scan )); then
    scan_started=$(now_ms)
    uv run "${env_args[@]}" hobbyjogging-import review "${database_args[@]}" scan
    scan_ms=$(( $(now_ms) - scan_started ))
fi

if (( generate_dashboard )); then
    dashboard_started=$(now_ms)
    if [[ -n "$database" ]]; then
        HOBBYJOGGING_DB="$database" \
            uv run "${env_args[@]}" python -m hobbyjogging_report dashboard
    else
        uv run "${env_args[@]}" python -m hobbyjogging_report dashboard
    fi
    dashboard_ms=$(( $(now_ms) - dashboard_started ))
fi

timing=()
if (( generate_maintenance )); then
    timing+=("maintain $(format_ms "$maintenance_ms")")
fi
if (( generate_scan )); then
    timing+=("scan $(format_ms "$scan_ms")")
fi
if (( generate_dashboard )); then
    timing+=("dashboard $(format_ms "$dashboard_ms")")
fi
if (( ${#timing[@]} > 0 )); then
    joined=$(printf '%s, ' "${timing[@]}")
    printf '  timing:    %s\n' "${joined%, }"
fi
