#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
    cat <<'EOF'
Usage:
  ./demo.sh

Builds the public demo site from a synthetic database:

  build/demo.db   deterministic synthetic training database
  build/site      self-contained static dashboard

No personal data is read: the database is generated from scratch and the
canonical HOBBYJOGGING_DB is never opened. The GitHub Pages workflow runs this
script; run it locally to preview the demo.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

mkdir -p build

# No --env-file: CI has no .env, and the demo must not read one.
uv run python -m hobbyjogging_report demo-db \
    --out "$ROOT/build/demo.db" \
    --force

HOBBYJOGGING_DB="$ROOT/build/demo.db" \
    uv run python -m hobbyjogging_report dashboard \
    --output "$ROOT/build/site" \
    --demo-label "Synthetic demo data — not a real athlete"

echo "Demo site: $ROOT/build/site"
