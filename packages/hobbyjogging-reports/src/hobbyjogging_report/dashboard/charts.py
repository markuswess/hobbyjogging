"""Dashboard-specific chart helpers.

The chart builders themselves live in :mod:`hobbyjogging_report.charts` so the
CLI and the dashboard render exactly the same figure.
"""

from plotly.offline import get_plotlyjs


def plotly_js() -> str:
    """Return the plotly library source to bundle with the site."""
    return get_plotlyjs()
