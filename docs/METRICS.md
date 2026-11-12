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

## Candidates

Nothing here: ideas live in `experiments/` until they pass the gate.

## Rejected

One line per rejected idea — name, reason, date — so it is not re-litigated.
