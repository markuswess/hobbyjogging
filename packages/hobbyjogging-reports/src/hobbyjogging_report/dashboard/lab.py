"""Dashboard Lab tab: experiments, scripts, and the metric registry."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..html import esc
from .docs import headings, render_markdown

LAB_DIR = Path(__file__).resolve().parents[5] / "experiments"
README_PATH = LAB_DIR / "README.md"
METRICS_PATH = Path(__file__).resolve().parents[5] / "docs" / "METRICS.md"

INTRO = (
    "The lab is where metric ideas are explored before promotion. Experiments "
    "are throwaway scripts; only ideas that pass the gate in the metric "
    "registry below become package code and dashboard numbers."
)


@dataclass(frozen=True)
class LabSection:
    """Rendered lab cards for the dashboard."""

    intro_html: str
    readme_html: str
    scripts_html: str
    metrics_html: str


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


def _promoted_metrics(tokens):
    for token in tokens:
        if token["level"] == 2 and token["name"] == "Promoted":
            yield from headings(token.get("children", []), 3)
            return


def _toc(readme_tokens, metric_tokens) -> str:
    readme_items = "".join(
        f'<li><a href="#{token["id"]}">{token["name"]}</a></li>'
        for token in headings(readme_tokens, 2)
    )
    metric_items = "".join(
        f'<li><a href="#{token["id"]}">{token["name"]}</a></li>'
        for token in _promoted_metrics(metric_tokens)
    )

    if not readme_items and not metric_items:
        return ""

    groups = []
    if readme_items:
        groups.append(
            "<h3>Lab notebook</h3>"
            f"<ul>{readme_items}</ul>"
        )
    if metric_items:
        groups.append(
            "<h3>Metrics</h3>"
            f"<ul>{metric_items}</ul>"
        )

    return (
        '<nav class="toc">'
        "<h2>Contents</h2>"
        + "".join(groups)
        + "</nav>"
    )


def build_lab_section() -> LabSection:
    """Render the experiments notebook, its scripts, and the metrics."""
    readme_html = (
        '<p class="muted">experiments/README.md is not available in this '
        "installation.</p>"
    )
    readme_tokens = []

    if README_PATH.exists():
        readme_html, readme_tokens = render_markdown(
            README_PATH.read_text(encoding="utf-8").replace(
                "../docs/METRICS.md",
                "lab.html",
            ),
            "lab-",
        )

    metrics_html = (
        '<p class="muted">docs/METRICS.md is not available in this '
        "installation.</p>"
    )
    metric_tokens = []

    if METRICS_PATH.exists():
        metrics_html, metric_tokens = render_markdown(
            METRICS_PATH.read_text(encoding="utf-8"),
            "metric-",
        )

    return LabSection(
        intro_html=f"<p>{INTRO}</p>{_toc(readme_tokens, metric_tokens)}",
        readme_html=readme_html,
        scripts_html=_scripts_html(),
        metrics_html=metrics_html,
    )
