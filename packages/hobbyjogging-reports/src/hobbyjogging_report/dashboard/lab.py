"""Dashboard Lab tab: the experiments notebook and script index."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..html import esc, markdown_to_html

LAB_DIR = Path(__file__).resolve().parents[5] / "experiments"
README_PATH = LAB_DIR / "README.md"

INTRO = (
    "The lab is where metric ideas are explored before promotion. Experiments "
    "are throwaway scripts; only ideas that pass the gate in the metric "
    "registry become package code and dashboard numbers."
)


@dataclass(frozen=True)
class LabSection:
    """Rendered lab cards for the dashboard."""

    intro_html: str
    readme_html: str
    scripts_html: str


def _docstring_summary(path: Path) -> str:
    """First line of a Python module docstring, if there is one."""
    match = re.match(
        r'\s*"""(.*?)"""',
        path.read_text(encoding="utf-8"),
        re.DOTALL,
    )

    if match is None:
        return ""

    return match.group(1).strip().splitlines()[0]


def _scripts_html() -> str:
    scripts = sorted(
        path
        for path in LAB_DIR.glob("*.py")
        if path.name != "__init__.py"
    )

    if not scripts:
        return '<p class="muted">No experiment scripts yet.</p>'

    items = []

    for path in scripts:
        summary = _docstring_summary(path)
        suffix = f" — {esc(summary)}" if summary else ""
        items.append(f"<li><code>{esc(path.name)}</code>{suffix}</li>")

    return "<ul>" + "".join(items) + "</ul>"


def build_lab_section() -> LabSection:
    """Render the experiments README and list its scripts."""
    if not README_PATH.exists():
        return LabSection(
            intro_html=f"<p>{INTRO}</p>",
            readme_html=(
                '<p class="muted">experiments/README.md is not available in '
                "this installation.</p>"
            ),
            scripts_html=_scripts_html(),
        )

    return LabSection(
        intro_html=f"<p>{INTRO}</p>",
        readme_html=markdown_to_html(
            README_PATH.read_text(encoding="utf-8").replace(
                "../docs/METRICS.md",
                "docs.html",
            ),
            demote=1,
        ),
        scripts_html=_scripts_html(),
    )
