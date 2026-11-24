#!/usr/bin/env python3
"""Fail when a package source file grows past its readability budget.

A source file stays under 1,000 lines. A few cohesive giants predate the
rule; they are allowlisted here, and an entry is removed when the file is
split, so the list only shrinks.

Run from the repository root:

    uv run python tools/check_size.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 1000
SOURCE_GLOBS = ("packages/*/src/**/*.py",)

# Known giants, kept only while they are still over the limit.
ALLOWLIST = {
    "packages/hobbyjogging-core/src/hobbyjogging_core/db/writer.py",
    "packages/hobbyjogging-import/src/hobbyjogging_import/runalyze_import.py",
    "packages/hobbyjogging-import/src/hobbyjogging_import/triage.py",
    "packages/hobbyjogging-reports/src/hobbyjogging_report/demo.py",
    "packages/hobbyjogging-reports/src/hobbyjogging_report/format.py",
}


def source_files() -> list[Path]:
    files = set()

    for pattern in SOURCE_GLOBS:
        files.update(ROOT.glob(pattern))

    return sorted(files)


def line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8").splitlines())


def main() -> int:
    files = source_files()
    sizes = {
        path.relative_to(ROOT).as_posix(): line_count(path)
        for path in files
    }
    problems = []

    for name, lines in sorted(sizes.items()):
        if lines <= LIMIT or name in ALLOWLIST:
            continue

        problems.append(
            f"{name}: {lines} lines (limit {LIMIT}); split it or add a "
            "justified allowlist entry"
        )

    for name in sorted(ALLOWLIST):
        if name not in sizes:
            problems.append(f"{name}: allowlisted file no longer exists")
        elif sizes[name] <= LIMIT:
            problems.append(
                f"{name}: {sizes[name]} lines, under the limit; remove the "
                "allowlist entry"
            )

    if problems:
        print("\n".join(problems))
        return 1

    print(
        f"file sizes ok: {len(files)} source files under {LIMIT} lines, "
        f"{len(ALLOWLIST)} allowlisted"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
