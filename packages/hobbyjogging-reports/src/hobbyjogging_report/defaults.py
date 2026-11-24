"""Athlete-tuned defaults, in one place.

These are defaults, not laws. Every one was chosen on this training log and
is printed next to the number it shapes, so a different athlete can see the
assumption without reading the source. The metric cards in
``docs/METRICS.md`` own the definition and the evidence; this module owns the
number.

The cross-source conflict tolerances (average HR 5 bpm, elevation 10 % / 20 m,
distance 1 % / 10 m) stay in ``hobbyjogging_core.import_rules`` beside the
field rules they belong to; ``NUMERIC_TOLERANCES`` re-exports them for the
settings report.

Changing a value here is a behavioural change: run the four suites, the demo
build and the affected report before committing it.
"""

from __future__ import annotations

import importlib

from hobbyjogging_core.import_rules import NUMERIC_TOLERANCES

_classify = importlib.import_module("hobbyjogging_core.classify")
_compare = importlib.import_module("hobbyjogging_report.analysis.compare")
_efficiency = importlib.import_module("hobbyjogging_report.analysis.efficiency")

# --- analysis -------------------------------------------------------------

# Above this RPE a session is always quality; exactly this RPE needs another
# signal. A run longer than 90 minutes is a long run, quality by itself.
QUALITY_RPE = _classify.QUALITY_RPE
LONGRUN_S = _classify.LONGRUN_S
SUBT_CATEGORIES = _classify.SUBT_CATEGORIES

# A steady efficiency aggregate needs at least this many runs.
EFFICIENCY_MIN_RUNS = _compare.EFFICIENCY_MIN_RUNS

# The efficiency band is 40–75 min; the resting baseline is a 365-day median
# bounded to a plausible range.
STEADY_MIN_DURATION_S = _efficiency.STEADY_MIN_DURATION_S
STEADY_MAX_DURATION_S = _efficiency.STEADY_MAX_DURATION_S
STEADY_BAND_LABEL = _efficiency.STEADY_BAND_LABEL
RESTING_HR_WINDOW_DAYS = _efficiency.RESTING_HR_WINDOW_DAYS
MIN_EXCESS_HR = _efficiency.MIN_EXCESS_HR
MIN_RESTING_HR = _efficiency.MIN_RESTING_HR
MAX_RESTING_HR = _efficiency.MAX_RESTING_HR

# --- charts ---------------------------------------------------------------

# The pace/HR scatters share one linear-speed x-axis; fits run across it.
PACE_HR_SPEED_RANGE = (2.0, 5.2)

# The compare chart shows this many recent years; older years fade out. The
# palette runs backwards from the athlete's newest year.
COMPARE_VISIBLE_YEARS = 5
COMPARE_COLOR_ANCHOR_YEAR = 2026

# --- dashboard windows ----------------------------------------------------

# Upcoming races shown on the overview.
RACE_DAYS = 180

# Recovery/health plots and the analysis tab look back this far.
RECOVERY_DAYS = 730
ANALYSIS_DAYS = 731
NSA_DAYS = 365
