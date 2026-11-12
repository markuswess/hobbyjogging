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
  number is comparable across paces, so subT categories and year-over-year
  comparisons are meaningful.
- **Validation**: `HR ≈ 52.5 + 26.2·v` (R² = 0.54 over 2,685 steady runs), with
  the intercept matching the median resting HR (51 bpm). `v/HR` spreads 11.3%
  across speed quartiles; `v/(HR − RHR)` spreads 3.3%. A 42-day baseline
  inflated March 2026 by 8% after the illness; 180/365/fixed baselines agree
  within 0.01.
- **Caveats**: RHR noise propagates (~5% for a 5 bpm error on a ~90 bpm
  difference) — a trend signal, not a per-run score. HR lag understates short
  reps, so compare same rep lengths and prefer ≥5 min. Heat, terrain and
  fatigue move it.
- **Rendered**: session report, `eff` activities column, subT work reps and
  summary tables, subT EWMA report, subT chart panel, compare tab.

### HR-speed efficiency line

- **Definition**: for each half of the runs, `HR = RHR + v·60/E`, where `v`
  is speed in m/s, `RHR` is the half's median 365-day resting-HR baseline, and
  `E` is the half's weighted efficiency (`Σdistance / Σexcess beats`) in
  **m/excess beat**. One parameter, no free intercept.
- **Baseline / thresholds**: resting HR from the same rolling 365-day median
  (expanding, `None` when absent) used by the efficiency metric; points
  without a baseline are left out of the line but stay in the scatter.
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
  efficiency lines, annotated with `E` and median RHR; the CLI prints the same
  parameters.

## Candidates

_None._

## Rejected

One line per rejected idea — name, reason, date — so it is not re-litigated.
