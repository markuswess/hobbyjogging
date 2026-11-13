"""Small, dependency-free HTML building blocks for the dashboard."""

from __future__ import annotations

from html import escape

import markdown


def esc(value) -> str:
    """Escape text for use in HTML text or attribute context."""
    return escape(str(value), quote=True)


def markdown_to_html(text: str, *, demote: int = 0) -> str:
    """Render a Markdown report fragment for embedding in a page.

    ``demote`` shifts headings down so report titles fit under the page's own
    heading. Fenced code and tables use the same extensions as the reports.
    """
    rendered = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )

    if demote:
        for level in range(6 - demote, 0, -1):
            rendered = rendered.replace(
                f"<h{level}>",
                f"<h{level + demote}>",
            ).replace(
                f"</h{level}>",
                f"</h{level + demote}>",
            )

    return rendered


def link(href: str, text: str) -> str:
    return f'<a href="{esc(href)}">{esc(text)}</a>'


def table(
    headers: list[str],
    rows: list[list[str]],
    *,
    numeric: tuple[int, ...] = (),
    empty: str | None = None,
) -> str:
    """Render a table.

    Cell values are treated as HTML; callers escape user data with :func:`esc`.
    """
    if not rows:
        return (
            f'<p class="muted">{esc(empty)}</p>'
            if empty is not None
            else ""
        )

    numeric_set = set(numeric)
    head = "".join(
        f'<th class="num">{esc(header)}</th>'
        if index in numeric_set
        else f"<th>{esc(header)}</th>"
        for index, header in enumerate(headers)
    )
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="num">{cell}</td>'
            if index in numeric_set
            else f"<td>{cell}</td>"
            for index, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )

    return (
        '<div class="table-wrap"><table>'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table></div>"
    )


def stat_grid(stats) -> str:
    """Render ``(label, value_html, delta)`` triples as cards."""
    cards = []

    for label, value, delta in stats:
        delta_html = (
            f'<div class="muted">{esc(delta)}</div>'
            if delta
            else ""
        )
        cards.append(
            '<div class="card">'
            f'<div class="muted">{esc(label)}</div>'
            f'<div class="stat-value">{value}</div>'
            f"{delta_html}"
            "</div>"
        )

    return '<div class="grid">' + "".join(cards) + "</div>"


def card(title: str | None, body: str) -> str:
    heading = f"<h2>{esc(title)}</h2>" if title else ""
    return f'<section class="card">{heading}{body}</section>'


def chart(body: str) -> str:
    return f'<div class="chart">{body}</div>'


CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.45;
  background: #f6f7f9;
  color: #1f2933;
}
header {
  background: #1f2933;
  color: #fff;
  padding: 14px 24px;
}
header .brand { font-weight: 650; margin-right: 22px; }
nav a {
  color: #cbd2d9;
  text-decoration: none;
  margin-right: 16px;
}
nav a.active, nav a:hover { color: #fff; }
main { max-width: 1180px; margin: 0 auto; padding: 24px; }
.demo-banner {
  margin-bottom: 16px;
  padding: 10px 14px;
  border: 1px solid #e0a800;
  border-radius: 6px;
  background: #fff3cd;
  color: #664d03;
  font-weight: 600;
}
h1 { margin: 0 0 18px; font-size: 1.7rem; }
h2 { margin: 0 0 12px; font-size: 1.2rem; }
h3 { margin: 18px 0 8px; font-size: 1rem; }
a { color: #1769aa; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}
.card {
  background: #fff;
  border: 1px solid #e4e7eb;
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 18px;
}
.stat-value { font-size: 1.55rem; font-weight: 650; }
.muted { color: #616e7c; font-size: 0.9rem; }
.banner {
  border-radius: 8px;
  padding: 11px 14px;
  margin-bottom: 18px;
  font-size: 0.95rem;
}
.banner.ok { background: #e3f9e5; color: #1b5e20; }
.banner.warn { background: #fff4e5; color: #8a4b00; }
.banner.bad { background: #ffe3e3; color: #8a1f1f; }
.table-wrap { overflow-x: auto; }
table {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
  font-size: 0.92rem;
}
th, td {
  padding: 8px 10px;
  border-bottom: 1px solid #e4e7eb;
  text-align: left;
  vertical-align: top;
}
th { background: #eef1f4; font-weight: 600; }
th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
.chart {
  background: #fff;
  border: 1px solid #e4e7eb;
  border-radius: 10px;
  padding: 8px;
  margin-bottom: 18px;
}
pre.description {
  white-space: pre-wrap;
  background: #f8f9fa;
  border: 1px solid #e4e7eb;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
}
.report h1, .report h2, .report h3, .report h4 {
  margin: 16px 0 8px;
  line-height: 1.25;
}
.report h2 { font-size: 1.3rem; }
.report h3 { font-size: 1.1rem; }
.report h4 { font-size: 1rem; }
.report p { margin: 8px 0; }
.report ul, .report ol { margin: 8px 0 8px 22px; }
.report blockquote {
  margin: 12px 0;
  padding: 8px 12px;
  border-left: 3px solid #cbd2d9;
  background: #f8f9fa;
  color: #616e7c;
}
.report pre {
  white-space: pre-wrap;
  background: #f8f9fa;
  border: 1px solid #e4e7eb;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
}
.report code { font-size: 0.9em; }
.report table { margin: 10px 0; }
.toc { margin: 8px 0 0; }
.toc h3 { margin-top: 14px; }
.toc ul { columns: 2; margin: 6px 0 0 20px; padding: 0; }
.toc li { break-inside: avoid; margin: 3px 0; }
.split { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
@media (max-width: 800px) { .split { grid-template-columns: 1fr; } }
footer {
  color: #616e7c;
  font-size: 0.85rem;
  margin-top: 30px;
  padding-top: 14px;
  border-top: 1px solid #e4e7eb;
}
"""

NAV = (
    ("overview", "index.html", "Overview"),
    ("activities", "activities.html", "Activities"),
    ("performance", "performance.html", "Performance"),
    ("gear", "gear.html", "Gear"),
    ("recovery", "recovery.html", "Recovery and Health"),
    ("nsa", "nsa.html", "NSA"),
    ("analysis", "analysis.html", "Analysis"),
    ("compare", "compare.html", "Compare"),
    ("docs", "docs.html", "Docs"),
    ("lab", "lab.html", "Lab"),
    ("health", "health.html", "Data Health"),
)


def page(
    *,
    title: str,
    body: str,
    generated_at: str,
    health_html: str,
    active: str,
    root: str = "",
    plotly: bool = False,
    demo_label: str | None = None,
) -> str:
    """Render a complete dashboard page.

    ``root`` is the relative prefix to the site root (``../`` on detail
    pages). User-provided text must already be escaped by the caller.
    """
    nav = "".join(
        (
            f'<a href="{root}{href}" class="active">{esc(label)}</a>'
            if key == active
            else f'<a href="{root}{href}">{esc(label)}</a>'
        )
        for key, href, label in NAV
    )
    plotly_script = (
        f'<script src="{root}plotly.min.js"></script>' if plotly else ""
    )
    demo_banner = (
        f'<div class="demo-banner">{esc(demo_label)}</div>'
        if demo_label
        else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} · hobbyjogging</title>
<style>{CSS}</style>
{plotly_script}
</head>
<body>
<header>
  <nav><span class="brand">hobbyjogging</span>{nav}</nav>
</header>
<main>
{demo_banner}
{health_html}
<h1>{esc(title)}</h1>
{body}
<footer>Generated {esc(generated_at)}</footer>
</main>
</body>
</html>
"""
