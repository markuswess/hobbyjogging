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

The candidate list lives in `experiments/README.md`; this file records the
promoted and rejected cards and the reference catalogue of everything else
the reports compute.

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
  steady aggregates use a fixed **40–75 min** band, and a run counts as steady
  only when it is non-quality (unknown/unclassified runs count; intervals,
  races, long runs, progressions and fartlek do not). The floor sits at 40 min
  because the `+135/T` term makes a 40-minute run read about 1.5 % lower than a
  60-minute one — inside the band that bias is acceptable while the band is
  printed; lowering it added 26 steady runs over the last year (108 → 134) and
  314 all-time (1,165 → 1,479) while the aggregate moved by 0.002 and 0.001.
  The band is printed next to every aggregate, so two numbers are never read as
  comparable when they come from different bands. Session and daily efficiency
  stay raw per-activity values and are deliberately unbanded.
- **Comparability**: whole-session interval averages are not comparable to
  steady runs; compare intervals within a fixed protocol or through work-rep
  efficiency. Period, category, overview, compare and pace/HR efficiency lines
  use the same steady 40–75 min band, so their aggregates can be compared with
  each other but not with a raw session number or another run length.
- **Rendered**: session report and daily compact line (raw per activity),
  `eff` activities column, period/category reports (steady 40–75 min),
  compare text report and tab (steady 40–75 min), overview EWMA row,
  pace/HR efficiency lines, subT work reps and summary tables (work-rep
  efficiency, labelled as such), subT EWMA report, subT chart panel. The
  pace/HR scatter shows all runs; the steady 40–75 min points that feed the
  dashed efficiency lines carry a dark outline and the chart note says so.

### HR-speed efficiency line

- **Definition**: for each half of the runs, `HR = RHR + v·60/E`, where `v`
  is speed in m/s, `RHR` is the half's median 365-day resting-HR baseline, and
  `E` is the half's weighted efficiency (`Σdistance / Σexcess beats`) over
  **steady runs in the 40–75 min band**, in **m/excess beat**. One parameter,
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

### Running-only load

- **Definition**: daily training load comes from the canonical `training_load`
  (Intervals' `icu_training_load`). The running-fitness series sums **runs
  only**; rides and other cross-training are drawn as a separate context stack
  and carry **no transfer factor**.
- **Baseline / thresholds**: 7-, 42- and 182-day EWMAs (fatigue, fitness,
  base). The 7-day line is not used to set the chart ceiling. Planned load is
  split by sport and projected through the calendar.
- **Informs**: whether the running-load trend explains aerobic efficiency, and
  whether a cycling-heavy block should count toward running fitness. It does
  not: cross load is context, so a hard ride week must not read as a running
  build.
- **Validation**: `experiments/cross_training_load.py`, 2022-09..2026-11.
  Cross load is 9–26 % of annual load. 42-day running/cross correlations with
  steady efficiency are +0.04 / −0.06 raw and +0.05 / −0.04 year-adjusted;
  adding cross load gives R² 0.074 with a negative coefficient and a bootstrap
  transfer factor of −10..+25; the transfer grid is flat at R² 0.071–0.073
  with best `k = 0.0`. Weeks with ≥20 % cross load read 2.409 vs 2.445
  efficiency, but that is confounded.
- **Caveats**: load starts in 2019 and efficiency in 2022, so the cycling-heavy
  2020 phase is not covered by the comparison. The load signal itself is weak,
  so this rejects a positive transfer factor rather than proving there is
  none. Training load is a platform-derived session score, not a physiological
  measurement; a source without it (FIT alone) leaves the series empty.
- **Rendered**: load chart (running/cross stacked, running-only EWMAs),
  overview `Run load / week`, the compare load metric, planned load split by
  sport, and the analysis charts' planned-load projections. Code landed in
  `66dd91b`.

### Effective VO2max (HR/economy)

- **Definition**: a session-level estimate from running economy and heart-rate
  fraction, the ACSM running oxygen cost divided by the fraction of max HR:
  `VO2max = (3.5 + 0.2 · speed_m_min) / (avg_hr / max_hr)`. `max_hr` is the
  running max HR from the `athlete_thresholds` snapshot in force on the
  session's day (the earliest snapshot covers earlier days). The primary series
  uses **all runs**; a second series restricts to the steady 40–75 min,
  non-quality road runs.
- **Baseline / thresholds**: a run is dropped without average HR or duration,
  outside 1.5–6.0 m/s, or with an HR fraction outside 0.5–0.95. Same-day runs
  are averaged, days without a run carry the last value forward, and the
  standing value is a 42- and 182-day EWMA (`alpha = 1 − exp(−1/days)`) with
  910 days of warm-up. Garmin and Runalyze values are comparison series and
  never feed the estimate.
- **Informs**: whether aerobic capacity is moving, independent of which watch
  recorded the run. It replaces the Garmin-only overview line, which mixes
  device generations and per-sport estimates.
- **Validation**: `experiments/vo2max_estimates.py`, 2019–2026. All runs
  n=2,821, mean 59.3: r +0.95 against Runalyze and 42-day r +0.76 against
  Garmin; steady 40–75 n=1,092, mean 59.7: +0.91 / +0.67. The device split
  explains the weaker whole-period fit — FR645 (n=888) raw r +0.26 and 42-day
  r +0.47 (RMSE 2.41) against Enduro (n=1,338) +0.47 / +0.91 (RMSE 1.44); Garmin
  changes 607 of 892 FR645 runs (mean |Δ| 0.449) but only 245 of 1,340 Enduro
  (0.067), while Runalyze changes 489 of 497 (3.50). Runalyze's stored value
  already applies a 0.93 correction (stored mean 61.3, uncorrected 65.9) and
  the estimate aligns with the corrected value. Against Daniels race VDOT over
  all 37 road races, VDOT − estimate is **−0.43 mean / −0.07 median**, versus
  −1.46 / −1.11 for Garmin and −3.63 / −3.49 for Runalyze. Distance-corrected
  pacing variants were not supported (raw pace is closest, RMSE 2.02), and the
  HR-reserve variant overestimates (~73.5) and was rejected.
- **Caveats**: it is an ACSM-economy approximation, not a lab VO2max, and a
  single session value is noisy — read the 42-day EWMA, not the dot. The
  FR645 era stays visibly noisier than the Enduro era. There is no GAP, so
  hilly runs read low, and no streams, so pace/HR lag is unmodelled. It needs
  an average HR and a running max-HR snapshot; a run without either is skipped.
  Runalyze's number carries its own internal correction, so it is a reference,
  not a second estimate to merge.
- **Rendered**: overview's second axis (42-day black, 182-day grey) and the
  overview report's latest 42/182 values; the Performance "VO2max methods"
  card and `charts.sh vo2max` (all runs, steady band, Garmin by device,
  Runalyze and 42-day mean, race VDOT). The Compare tab keeps its raw
  Garmin-by-year chart, which is a different question.

## Reference catalogue

Everything the reports compute that is **not** a promoted card. One line per
number or method: what it is, the module that computes it, and where it
renders. A row earns a card above only by passing the gate; this table is the
inverse map, so any figure on a page can be traced to its code path. It is
hand-written and checked in the periodic cleanup (root item 28) — a test that
greps prose would be more fragile than the drift it prevents.

| number or method | computed in | rendered |
|---|---|---|
| Daily and weekly load, running-only vs cross | `analysis/load.py` | load chart, overview `Run load / week`, compare |
| 7/42/182-day EWMAs of hard and total time | `analysis/zones.py`, `series.ewma` | overview, analysis charts, compare |
| Weekly volume, time and zone shares | `analysis/averages.py`, `analysis/zones.py` | overview, period, compare |
| Planned volume/time/load projected through the calendar | `analysis/planned.py`, `analysis/zones.py` | analysis charts, plan vs actual |
| Session RPE and its weekly average | `analysis/rpe.py` | load chart overlay |
| Zone-time normalization across era configs | `analysis/zones.py` | zone tables and charts |
| Recovery bands (HRV, resting HR, sleep) from robust medians | `analysis/baseline.py`, `analysis/recovery.py` | recovery tab and report |
| Effective VO2max (all runs and steady 40–75), 42/182-day EWMAs; Garmin by device, Runalyze and race VDOT beside it | `analysis/vo2max.py` | overview axis, Performance methods card, `vo2max` chart; compare keeps raw Garmin |
| Race bucket and PB qualification (2 % of standard distance) | `analysis/races.py` | races report, Performance tab |
| Riegel fit, reference anchoring and equivalent times | `analysis/races.py` | race chart, equivalents table |
| Official race pair preferred over measured values | `analysis/races.py` | races report, PB tables |
| subT work-rep selection and rep-level efficiency | `analysis/subt.py` | subT report and chart |
| subT weighted-efficiency EWMA | `analysis/subt_ewma.py` | subT EWMA report and panel |
| Per-era threshold snapshots and threshold-relative pace | `analysis/thresholds.py` | threshold chart, subT `Δ threshold` |
| Pace/HR scatter, trends and per-year efficiency lines | `analysis/pace_hr.py` | analysis and compare charts |
| Year/month comparison aggregates | `analysis/compare.py` | compare report and tab |
| Per-year data coverage (activities with a weather row) | `analysis/coverage.py` | data-health tab |
| Device usage and change dates | `analysis/devices.py` | gear tab, session line |
| Device identity: FIT-first, provider name maps to the unique FIT model, app names are never devices | `hobbyjogging_import.devices` | imports, session and gear labels |
| Equipment usage, coverage and retirement candidates | `analysis/equipment.py` | gear tab and report |
| Running streaks (run days of at least 10 min) | `analysis/streaks.py` | streaks report, analysis tab |
| Workout classifier and the stored-set display kind | `hobbyjogging_core.classify` | category tables, every report |
| Work-interval filter and its usable-rep guards | `hobbyjogging_core.classify` | subT, intervals detail |
| Matching ladder and the exact-twin rule | `hobbyjogging_import.matching` | imports, review queue |
| Field ownership, ranked authority and tolerances | `hobbyjogging_core.import_rules` | imports, settings report |
| Quality rules and review fingerprints | `hobbyjogging_import.quality` | review queue, data health |
| Source create policy and text targets | `sources.toml`, `hobbyjogging_core.sources_config` | `sources` / `settings` |

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
