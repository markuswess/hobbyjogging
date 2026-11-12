#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# The lab is interactive, so unlike reports.sh it must not capture stdout.
exec uv run --env-file .env python -m hobbyjogging_report.shell "$@"
