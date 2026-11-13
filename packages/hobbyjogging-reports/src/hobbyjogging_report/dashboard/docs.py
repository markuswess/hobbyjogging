"""Dashboard Docs tab: the package README."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import markdown
from markdown.extensions.toc import slugify

README_PATH = Path(__file__).resolve().parents[3] / "README.md"

INTRO = (
    "The report reference, rendered from the repository README. Metric "
    "definitions and their promotion history live on the Lab tab."
)


@dataclass(frozen=True)
class DocsSection:
    """Rendered docs for the dashboard tab."""

    intro_html: str
    readme_html: str
    missing: bool = False


def render_markdown(text: str, prefix: str):
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


def headings(tokens, level: int):
    for token in tokens:
        if token["level"] == level:
            yield token
        yield from headings(token.get("children", []), level)


def _toc(readme_tokens) -> str:
    readme_items = "".join(
        f'<li><a href="#{token["id"]}">{token["name"]}</a></li>'
        for token in headings(readme_tokens, 2)
    )

    return (
        '<nav class="toc">'
        "<h2>Contents</h2>"
        "<h3>Reports guide</h3>"
        f"<ul>{readme_items}</ul>"
        "</nav>"
    )


def build_docs_section() -> DocsSection:
    """Read and render the README."""
    if not README_PATH.exists():
        return DocsSection(
            intro_html=f"<p>{INTRO}</p>",
            readme_html=(
                '<p class="muted">README.md is not available in this '
                "installation.</p>"
            ),
            missing=True,
        )

    readme_html, readme_tokens = render_markdown(
        README_PATH.read_text(encoding="utf-8"),
        "readme-",
    )

    return DocsSection(
        intro_html=(
            f"<p>{INTRO}</p>"
            f"{_toc(readme_tokens)}"
        ),
        readme_html=readme_html,
    )
