"""Shared plot tokens for dashboard charts."""

from __future__ import annotations

# Bars
EASY_COLOR = "#8ecae6"
HARD_COLOR = "#ff6b6b"
UNZONED_COLOR = "#d9d9d9"
EASY_PLANNED_COLOR = "rgba(142, 202, 230, 0.45)"
HARD_PLANNED_COLOR = "rgba(255, 107, 107, 0.45)"
UNZONED_PLANNED_COLOR = "rgba(217, 217, 217, 0.6)"
EASY_EDGE = "#0077b6"
HARD_EDGE = "#d00000"
UNZONED_EDGE = "#969696"

# Averages
EASY_LINE_COLORS = {
    7: "#48cae4",
    42: "#0077b6",
    182: "#023e8a",
}
TOTAL_LINE_COLORS = EASY_LINE_COLORS
HARD_LINE_COLORS = {
    7: "#e63946",
    42: "#d00000",
    182: "#7f1d1d",
}
LINE_STYLES = {7: "solid", 42: "dash", 182: "dashdot"}
LINE_WIDTHS = {7: 1.8, 42: 1.8, 182: 2.4}
RPE_LINE_COLORS = {
    7: "#2ca02c",
    42: "#1b7837",
    182: "#00441b",
}

# Planned / projected overlays
PLANNED_FILL_ALPHA = 0.45
PLANNED_HATCH = "//"
PLANNED_PATTERN = "/"
PROJECTED_OPACITY = 0.55

# Fixed axes keep periods comparable instead of autoscaling.
VOLUME_Y_MAX = 130.0
TIME_Y_MAX = 10.0
LOAD_Y_MAX = 150.0
RPE_PER_LOAD = 25.0  # one RPE point maps to 25 load units on the right axis
SUBT_PACE_RANGE = (260.0, 195.0)  # 4:20 .. 3:15 min/km, slow at the bottom
SUBT_HR_RANGE = (140.0, 180.0)
CLIPPED_COLOR = "#7f7f7f"

# Recovery readiness bands (background fills and legend markers).
RECOVERY_BAND_COLORS = {
    "normal": "rgba(46, 139, 87, 0.10)",
    "watch": "rgba(255, 193, 7, 0.16)",
    "alert": "rgba(220, 53, 69, 0.10)",
}
RECOVERY_BAND_MARKERS = {
    "normal": "#2e8b57",
    "watch": "#ffc107",
    "alert": "#dc3545",
}
