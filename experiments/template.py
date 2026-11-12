"""Experiment template: copy to ``experiments/<name>.py``.

Rules: throwaway, not imported by any package, no tests. Print a table, save
plots to ``data/lab/``, and promote only what survives ``docs/METRICS.md``.
"""

from datetime import date, timedelta

import plotly.graph_objects as go

from hobbyjogging_report.shell import save, table
from hobbyjogging_report.sources import create_source


def main() -> None:
    end = date.today()
    start = end - timedelta(days=365 * 3)

    with create_source() as source:
        runs = [
            activity
            for activity in source.activities(start, end)
            if activity.type == "run"
        ]

    rows = []
    for run in runs:
        if not (run.distance_m and run.duration_s and run.avg_hr):
            continue
        pace_s_per_km = run.duration_s / (run.distance_m / 1000)
        rows.append(
            (run.date, run.distance_m / 1000, pace_s_per_km, run.avg_hr)
        )

    print(f"{len(rows)} runs with distance, time and HR")
    table(rows[:10], headers=["date", "km", "s/km", "hr"])

    figure = go.Figure(
        go.Scatter(
            x=[row[2] for row in rows],
            y=[row[3] for row in rows],
            mode="markers",
            marker={"size": 5, "opacity": 0.5},
        )
    )
    figure.update_xaxes(title_text="pace (s/km)", autorange="reversed")
    figure.update_yaxes(title_text="average HR (bpm)")
    save(figure, "template-pace-hr")


if __name__ == "__main__":
    main()
