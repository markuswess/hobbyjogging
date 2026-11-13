"""Dashboard Docs tab: package README plus the metric registry."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import markdown
from markdown.extensions.toc import slugify

README_PATH = Path(__file__).resolve().parents[3] / "README.md"
METRICS_PATH = (
    Path(__file__).resolve().parents[5] / "docs" / "METRICS.md"
)

INTRO = (
    "The report reference and the metric registry, rendered from the "
    "repository Markdown. Metric cards define the formula, baseline, "
    "thresholds, and caveats behind the dashboard numbers."
)


@dataclass(frozen=True)
class DocsSection:
    """Rendered docs for the dashboard tab."""

    intro_html: str
    readme_html: str
    metrics_html: str
    missing: bool = False


def _render(text: str, prefix: str):
    """Render Markdown with prefixed heading ids and demoted headings."""

    def prefixed_slugify(value, separator):
        return f"{prefix}{slugify(value, separator)}"

    parser = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        extension_configs={
            "toc": {"slugify": prefixed_slugify},
        },
    )
    html = parser.convert(text)
    html = re.sub(
        r"<(/?)(h[1-6])([^>]*)>",
        lambda match: (
            f"<{match.group(1)}h"
            f"{min(6, int(match.group(2)[1]) + 1)}"
            f"{match.group(3)}>"
        ),
        html,
    )
    return html, parser.toc_tokens


def _headings(tokens, level: int):
    for token in tokens:
        if token["level"] == level:
            yield token
        yield from _headings(token.get("children", []), level)


def _promoted_metrics(tokens):
    for token in tokens:
        if token["level"] == 2 and token["name"] == "Promoted":
            yield from _headings(token.get("children", []), 3)
            return


def _toc(readme_tokens, metric_tokens) -> str:
    readme_items = "".join(
        f'<li><a href="#{token["id"]}">{token["name"]}</a></li>'
        for token in _headings(readme_tokens, 2)
    )
    metric_items = "".join(
        f'<li><a href="#{token["id"]}">{token["name"]}</a></li>'
        for token in _promoted_metrics(metric_tokens)
    )

    return (
        '<nav class="toc">'
        "<h2>Contents</h2>"
        "<h3>Reports guide</h3>"
        f"<ul>{readme_items}</ul>"
        "<h3>Metrics</h3>"
        f"<ul>{metric_items}</ul>"
        "</nav>"
    )


def build_docs_section() -> DocsSection:
    """Read and render the README and metrics registry."""
    missing = not README_PATH.exists() or not METRICS_PATH.exists()

    if missing:
        return DocsSection(
            intro_html=f"<p>{INTRO}</p>",
            readme_html=(
                '<p class="muted">README.md is not available in this '
                "installation.</p>"
            ),
            metrics_html=(
                '<p class="muted">docs/METRICS.md is not available in this '
                "installation.</p>"
            ),
            missing=True,
        )

    readme_html, readme_tokens = _render(
        README_PATH.read_text(encoding="utf-8"),
        "readme-",
    )
    metrics_html, metric_tokens = _render(
        METRICS_PATH.read_text(encoding="utf-8"),
        "metric-",
    )

    return DocsSection(
        intro_html=(
            f'<p>{INTRO}</p>'
            f'{_toc(readme_tokens, metric_tokens)}'
        ),
        readme_html=readme_html,
        metrics_html=metrics_html,
    )
