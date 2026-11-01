#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./db.sh                 open the database interactively
  ./db.sh ".tables"       run a SQLite dot command
  ./db.sh "SELECT ..."    run a query

The database path comes from HOBBYJOGGING_DB in .env, or from the current
environment if set. Otherwise it falls back to data/hobbyjogging.db.

Examples:
  ./db.sh ".tables"
  ./db.sh ".schema activities"
  ./db.sh "SELECT local_date, sport, name FROM activities
           ORDER BY local_date DESC LIMIT 10;"
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "error: sqlite3 is not installed" >&2
    exit 1
fi

override_db="${HOBBYJOGGING_DB:-}"

if [[ -f .env ]]; then
    # shellcheck disable=SC1091
    source .env
fi

db="${override_db:-${HOBBYJOGGING_DB:-data/hobbyjogging.db}}"
db="${db/#\~/$HOME}"

if [[ "$db" != /* ]]; then
    db="$ROOT/$db"
fi

if [[ ! -f "$db" ]]; then
    echo "error: database not found: $db" >&2
    exit 1
fi

exec sqlite3 -header -column "$db" "$@"
