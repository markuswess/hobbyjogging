"""Small ANSI renderer for the Markdown reports.

The renderer is intentionally dependency-free. It handles the Markdown
used by the training reports: headings, bullet lists, emphasis, fenced
code blocks, and pipe tables. The output is for terminal display only;
clipboard data should always be the original Markdown.
"""

import os
import re
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
BRIGHT_CYAN = "\033[96m"
BLUE = "\033[34m"
YELLOW = "\033[33m"

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
BULLET_RE = re.compile(r"^(\s*)[-*]\s+(.*)$")
NUMBERED_RE = re.compile(r"^(\s*)(\d+\.)\s+(.*)$")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
CODE_RE = re.compile(r"`([^`]+)`")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
SEPARATOR_RE = re.compile(r"^:?-{3,}:?$")
DATE_RANGE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}\s*→\s*\d{4}-\d{2}-\d{2}$"
)
FENCE_RE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")


def _style(text: str, code: str, color: bool) -> str:
    if not color or not code:
        return text
    return f"{code}{text}{RESET}"


def _plain_inline(text: str) -> str:
    text = BOLD_RE.sub(r"\1", text)
    text = CODE_RE.sub(r"\1", text)
    text = LINK_RE.sub(r"\1", text)
    return text


def _inline(text: str, color: bool) -> str:
    if not color:
        return _plain_inline(text)

    text = BOLD_RE.sub(
        lambda match: _style(match.group(1), BOLD, True),
        text,
    )
    text = CODE_RE.sub(
        lambda match: _style(match.group(1), YELLOW, True),
        text,
    )
    text = LINK_RE.sub(
        lambda match: (
            f"{match.group(1)} "
            f"{DIM}({match.group(2)}){RESET}"
        ),
        text,
    )
    return text


def _width(text: str) -> int:
    return len(_plain_inline(text))


def _split_row(line: str) -> list[str]:
    value = line.strip()

    if value.startswith("|"):
        value = value[1:]

    if value.endswith("|"):
        value = value[:-1]

    return [cell.strip() for cell in value.split("|")]


def _alignment(cell: str) -> str:
    cell = cell.strip()

    if cell.startswith(":") and cell.endswith(":"):
        return "center"

    if cell.endswith(":"):
        return "right"

    return "left"


def _render_row(
    cells: list[str],
    widths: list[int],
    aligns: list[str],
    color: bool,
    header: bool = False,
) -> str:
    rendered = []

    for cell, width, align in zip(cells, widths, aligns):
        gap = max(0, width - _width(cell))

        if align == "right":
            left, right = gap, 0
        elif align == "center":
            left = gap // 2
            right = gap - left
        else:
            left, right = 0, gap

        content = _inline(cell, color)

        if header:
            content = _style(content, BOLD + CYAN, color)

        rendered.append(" " * left + content + " " * right)

    return "│ " + " │ ".join(rendered) + " │"


def _render_table(lines: list[str], color: bool) -> list[str]:
    rows = [_split_row(line) for line in lines]
    ncols = max(len(row) for row in rows)
    rows = [row + [""] * (ncols - len(row)) for row in rows]

    separator = next(
        (
            index
            for index, row in enumerate(rows)
            if all(SEPARATOR_RE.match(cell) for cell in row)
        ),
        None,
    )

    aligns = ["left"] * ncols

    if separator is not None:
        aligns = [_alignment(cell) for cell in rows[separator]]
        data_rows = [
            row for index, row in enumerate(rows)
            if index != separator
        ]
    else:
        data_rows = rows

    if not data_rows:
        return []

    widths = [
        max(3, max(_width(row[index]) for row in data_rows))
        for index in range(ncols)
    ]

    top = "┌" + "┬".join("─" * (width + 2) for width in widths) + "┐"
    middle = "├" + "┼".join(
        "─" * (width + 2) for width in widths
    ) + "┤"
    bottom = "└" + "┴".join(
        "─" * (width + 2) for width in widths
    ) + "┘"

    rendered = [top]

    for index, row in enumerate(data_rows):
        rendered.append(
            _render_row(
                row,
                widths,
                aligns,
                color,
                header=index == 0,
            )
        )

        if index == 0 and len(data_rows) > 1:
            rendered.append(middle)

    rendered.append(bottom)

    return rendered


def _render_code(block: list[str], indent: str, color: bool) -> list[str]:
    """Render fenced code lines with a dim gutter, never inline-styled."""
    rendered = []

    for line in block:
        gutter = _style("│ ", DIM, color)

        if line:
            rendered.append(f"{indent}{gutter}{line}")
        else:
            rendered.append(f"{indent}{_style('│', DIM, color)}")

    return rendered


def _parse_fence(line: str):
    match = FENCE_RE.match(line)

    if not match:
        return None

    indent, marker, info = match.groups()

    # A backtick fence's info string must not contain backticks.
    if marker[0] == "`" and "`" in info:
        return None

    return indent, marker, info.strip()


def _dedent(line: str, indent: str) -> str:
    """Remove up to ``indent`` leading spaces from a code line."""
    remaining = len(indent)

    while remaining and line.startswith(" "):
        line = line[1:]
        remaining -= 1

    return line


def _render_line(line: str, color: bool) -> str:
    if not line.strip():
        return ""

    heading = HEADING_RE.match(line)

    if heading:
        level = len(heading.group(1))
        text = heading.group(2).strip()

        if level == 1:
            rule = "━" * max(1, _width(text))
            return (
                f"{_style(text, BOLD + BRIGHT_CYAN, color)}\n"
                f"{_style(rule, DIM, color)}"
            )

        if level == 2:
            return _style(f"▌ {text}", BOLD + CYAN, color)

        if level == 3:
            return _style(f"  ▸ {text}", BOLD + BLUE, color)

        return _style(f"    {text}", BOLD, color)

    bullet = BULLET_RE.match(line)

    if bullet:
        indent, text = bullet.groups()
        return (
            f"{indent}{_style('•', CYAN, color)} "
            f"{_inline(text, color)}"
        )

    numbered = NUMBERED_RE.match(line)

    if numbered:
        indent, marker, text = numbered.groups()
        return (
            f"{indent}{_style(marker, CYAN, color)} "
            f"{_inline(text, color)}"
        )

    if DATE_RANGE_RE.match(line):
        return _style(line, DIM, color)

    if line.strip() in ("---", "***", "___"):
        return _style("─" * 40, DIM, color)

    if line.startswith("> "):
        return (
            f"{_style('│ ', CYAN, color)}"
            f"{_inline(line[2:], color)}"
        )

    return _inline(line, color)


def render_markdown(text: str, color: bool | None = None) -> str:
    """Render report Markdown for a terminal."""
    if color is None:
        color = (
            sys.stdout.isatty()
            and os.environ.get("NO_COLOR") is None
        )

    lines = text.splitlines()
    rendered = []
    index = 0

    while index < len(lines):
        line = lines[index]

        fence = _parse_fence(line)

        if fence:
            indent, marker, _ = fence
            block = []
            index += 1

            while index < len(lines):
                closing = _parse_fence(lines[index])

                if (
                    closing
                    and closing[1][0] == marker[0]
                    and len(closing[1]) >= len(marker)
                    and closing[2] == ""
                ):
                    index += 1
                    break

                block.append(_dedent(lines[index], indent))
                index += 1

            rendered.extend(_render_code(block, indent, color))
            continue

        if line.lstrip().startswith("|"):
            table = []

            while (
                index < len(lines)
                and lines[index].lstrip().startswith("|")
            ):
                table.append(lines[index])
                index += 1

            rendered.extend(_render_table(table, color))
            continue

        rendered.append(_render_line(line, color))
        index += 1

    result = "\n".join(rendered)

    if text.endswith("\n"):
        result += "\n"

    return result


def main() -> None:
    sys.stdout.write(render_markdown(sys.stdin.read()))


if __name__ == "__main__":
    main()
