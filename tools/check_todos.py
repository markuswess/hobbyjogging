#!/usr/bin/env python3
"""Check the cross-references between the todo lists.

Every package ``NEXT_UP.md`` points at root items by number ("root item 4",
"root #4"). Renumbering the root list silently breaks those pointers, so this
script fails when a reference names an item that does not exist and when a root
number appears twice.

Run from the repository root:

    uv run python tools/check_todos.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_LIST = ROOT / "docs" / "NEXT_UP.md"
PACKAGE_LISTS = sorted((ROOT / "packages").glob("*/NEXT_UP.md"))

ITEM_RE = re.compile(r"^(\d+)\. \*\*", re.MULTILINE)
REFERENCE_RE = re.compile(r"root\s+(?:item\s+)?#?(\d+)", re.IGNORECASE)


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def root_items(text: str) -> dict[int, int]:
    """Map each root item number to the line it starts on."""
    items: dict[int, int] = {}

    for match in ITEM_RE.finditer(text):
        items[int(match.group(1))] = line_of(text, match.start())

    return items


def broken_references(
    path: Path,
    known: dict[int, int],
) -> list[str]:
    """Return the references in one package list that name no root item."""
    text = path.read_text(encoding="utf-8")
    problems = []

    for match in REFERENCE_RE.finditer(text):
        number = int(match.group(1))

        if number not in known:
            problems.append(
                f"{path.relative_to(ROOT)}:{line_of(text, match.start())}: "
                f"root item {number} does not exist"
            )

    return problems


def duplicate_numbers(text: str) -> list[int]:
    """Root numbers that appear more than once (the mapping keeps the last)."""
    seen: dict[int, int] = {}

    for match in ITEM_RE.finditer(text):
        number = int(match.group(1))
        seen[number] = seen.get(number, 0) + 1

    return sorted(number for number, count in seen.items() if count > 1)


def main() -> int:
    root_text = ROOT_LIST.read_text(encoding="utf-8")
    known = root_items(root_text)
    problems = []

    for number in duplicate_numbers(root_text):
        problems.append(f"docs/NEXT_UP.md: root item {number} appears twice")

    for path in PACKAGE_LISTS:
        problems.extend(broken_references(path, known))

    if problems:
        print("\n".join(problems))
        return 1

    print(
        f"todo references ok: {len(known)} root items, "
        f"{len(PACKAGE_LISTS)} package lists"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
