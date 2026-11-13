# Metric registry

One card per metric, so a number cannot drift away from its definition, its
baseline and its known failure modes. Cards are deliberately short.

## Promotion gate

An idea starts in the lab (`./lab.sh`, `experiments/`) and is promoted only
when all four hold:

1. it answers a question that comes up repeatedly;
2. it is stable under known distortions (illness, heat, sparse data);
3. it beats the naive version on the real data;
4. it will be looked at weekly.

The candidate list lives in `experiments/README.md`; this file records only
what was promoted or rejected.

Promotion is staged: pure function in `analysis/` with tests → cheapest
renderer (a CLI report or one column) → live with it for a week → charts →
dashboard. The dashboard is the last step, never the first.

## Card template

```text
### <name>
- Definition: formula and units.
- Baseline / thresholds: windows, guards, and why.
- Informs: the decision it supports.
- Validation: the numbers that justified it.
- Caveats: when not to trust it.
- Rendered: session / activities / subT / compare / dashboard.
```

## Promoted

### Efficiency (m/excess beat)

- **Definition**: `distance_m / ((avg_hr − rhr) × duration_min)` — meters
  covered per heartbeat above resting. Higher is better; it is linear, unlike
  pace/HR or HR/pace, which are reciprocal and average badly.
- **Baseline**: resting HR = rolling 365-day median of
  `wellness_days.resting_hr`, expanding median when history is shorter, `None`
  when there is none at all. Guard: `avg_hr − rhr < 10` → `None`.
- **Informs**: aerobic efficiency trends. Because the offset is removed, the
  number is comparable across paces *within a duration band*, so subT
  categories and year-over-year comparisons are meaningful.
- **Validation**: `HR ≈ 52.5 + 26.2·v` (R² = 0.54 over 2,685 steady runs), with
  the intercept matching the median resting HR (51 bpm). `v/HR` spreads 11.3%
  across speed quartiles; `v/(HR − RHR)` spreads 3.3%. A 42-day baseline
  inflated March 2026 by 8% after the illness; 180/365/fixed baselines agree
  within 0.01.
- **Caveats**: RHR noise propagates (~5% for a 5 bpm error on a ~90 bpm
  difference) — a trend signal, not a per-run score. HR lag understates short
  reps, so compare same rep lengths and prefer ≥5 min. Heat, terrain and
  fatigue move it.
- **Duration**: duration-dependent, so never compare across run lengths
  unqualified. `excess HR = a + b·v + c/T + d·T` on 980 steady runs
  (2022-09..2026-11, 20–240 min) gives `c = +135 bpm·min` and
  `d = +0.072 bpm/min`: at a fixed pace, efficiency reads ~1.8% lower at
  90 min, 4% lower at 120 min and 8.5% lower at 180 min than at 60 min. Short
  runs are *not* inflated as a warm-up transient would suggest — the
  20–30 min group is dominated by recovery sessions, often a second run of the
  day, and reads slightly lower. Filtering by duration or dropping recovery
  runs lowers split-half reliability (0.68 → 0.48), so trends use all steady
  runs. A provisional +4% per hour beyond 60 min is a labelled estimate (±4%
  at 2 h); the model cannot separate cardiac drift from heat, dehydration and
  fatigue, so the correction factor is **parked** until streams or a
  heat/fatigue control can shrink the uncertainty below the effect.
  `experiments/efficiency_duration.py`. Reports act on this directly: the
  steady aggregates use a fixed **45–75 min** band, and a run counts as steady
  only when it is non-quality (unknown/unclassified runs count; intervals,
  races, long runs, progressions and fartlek do not). The band is printed next
  to every aggregate, so two numbers are never read as comparable when they
  come from different bands. Session and daily efficiency stay raw
  per-activity values and are deliberately unbanded.
- **Comparability**: whole-session interval averages are not comparable to
  steady runs; compare intervals within a fixed protocol or through work-rep
  efficiency. Period, category, overview, compare and pace/HR efficiency lines
  use the same steady 45–75 min band, so their aggregates can be compared with
  each other but not with a raw session number or another run length.
- **Rendered**: session report and daily compact line (raw per activity),
  `eff` activities column, period/category reports (steady 45–75 min),
  compare text report and tab (steady 45–75 min), overview EWMA row,
  pace/HR efficiency lines, subT work reps and summary tables (work-rep
  efficiency, labelled as such), subT EWMA report, subT chart panel. The
  pace/HR scatter shows all runs; the steady 45–75 min points that feed the
  dashed efficiency lines carry a dark outline and the chart note says so.

### HR-speed efficiency line

- **Definition**: for each half of the runs, `HR = RHR + v·60/E`, where `v`
  is speed in m/s, `RHR` is the half's median 365-day resting-HR baseline, and
  `E` is the half's weighted efficiency (`Σdistance / Σexcess beats`) over
  **steady runs in the 45–75 min band**, in **m/excess beat**. One parameter,
  no free intercept.
- **Baseline / thresholds**: resting HR from the same rolling 365-day median
  (expanding, `None` when absent) used by the efficiency metric; points
  without a baseline or outside the steady band are left out of the line but
  stay in the scatter.
- **Informs**: whether the pace/HR cloud behaves like a single efficiency
  value, and whether aerobic efficiency moved between the two periods.
- **Validation**: `experiments/hr_efficiency_line.py`, 1,262 steady runs
  (2022-09 .. 2026-11, median RHR 51): regression R² 0.676 / RMSE 7.76 bpm;
  efficiency line R² 0.725 / RMSE 7.14 (aerobic range only: 8.11 vs 7.52).
  Efficiency is flat across the first three speed quartiles (2.41–2.44,
  corr(eff, speed) −0.12) and drops ~5% in the top quartile.
- **Caveats**: the weighted aggregate (2.33) sits 3–6% above the
  regression-implied efficiency (2.19–2.27) because it weights by
  distance/excess beats while the regression weights every run equally;
  yearly drift (2.24 in 2022 → 2.39 in 2026) inflates both residuals. HR lag
  understates short reps, so compare same rep lengths.
- **Rendered**: pace/HR chart — the two free regression halves plus two dashed
  efficiency lines, annotated with `E`, median RHR and the steady band; the
  scatter still shows every run, and outlined points mark the steady-band
  inputs to the lines. The CLI prints the same parameters and the band.

## Rejected

One line per rejected idea — name, reason, date — so it is not re-litigated.

- **Efficiency frontier (best-run envelope)**, rejected 2026-11-13. The
  top-quartile quarterly envelope is a smoother level (SD 0.073 vs 0.086) but
  less reliable (split-half 0.60 vs 0.75) and tracks the trend worse (slope
  0.024 vs 0.042 per year, R² 0.18 vs 0.39); no top-share from 10 % to 50 %
  beats the average, and the sample-size bias was absent (raw-frontier
  correlation with quarter n was −0.19, not positive). It is a level shift,
  not extra signal. Evidence:
  `git show 143267d:experiments/efficiency_frontier.py` and
  `experiments/README.md`.
