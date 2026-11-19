# Experiments

Throwaway analysis for a metric idea. Nothing here is imported by a package,
tested, or wired into a report.

```bash
cp experiments/template.py experiments/<name>.py
uv run --env-file .env python experiments/<name>.py
```

Rules:

- One file per idea, self-contained and runnable.
- Print a table and save plots to `data/lab/` (gitignored) via
  `hobbyjogging_report.shell.table` / `save`.
- No tests, no `analysis/` exports, no CLI commands — an experiment must be
  deletable without touching anything else.
- Use `./lab.sh` for the interactive version of the same thing.
- If it survives the gate in [`docs/METRICS.md`](../docs/METRICS.md), promote
  it: pure function in `analysis/` plus tests, cheapest renderer first, then
  charts, then dashboard.
- If it does not, delete the file and leave a one-line "rejected" card so the
  idea is not re-litigated.

## Lab session ground rules

- **Scope.** The lab explores; promotion is a package/root step. Writes stay
  in `experiments/` and lab docs; never package code, schema, or reports.
- **Read-only data.** No imports, sync, maintenance, triage, or dashboard
  regeneration. Anything risky runs against a copy in `/tmp/opencode/`.
- **One idea, one question.** The docstring states the hypothesis, formula,
  guards, the naive baseline it must beat, and what would falsify it.
  Definition changes after looking at results are recorded as iterations.
- **Coverage first.** Print n, date span, and exclusions before any
  conclusion.
- **Canonical model.** Use `DataSource` and existing `analysis/` helpers; SQL
  is for feasibility checks, not the metric.
- **Stability.** Before proposing promotion, split by year, illness, and
  sparse-data periods, and check outlier and guard sensitivity.
- **Disposition.** Every idea ends as promote handoff, park (tested and
  deferred; keep the file), block (never started; name the missing
  prerequisite), or reject (delete the file). No open-ended results.
- **Cards.** The lab drafts promoted/rejected card text; the root session
  writes and commits the card in `docs/METRICS.md`.
- **Commits.** Finished experiments are committed here; never stage unrelated
  in-progress edits; do not push.
- **Minimal.** The smallest experiment that settles the question.
- **Impact per unit of effort.** Pick the highest-impact, lowest-workload idea
  next; the list order is not a schedule. An idea that unblocks or invalidates
  other measurements outranks a new one. Blocked items stay out of the queue
  until their prerequisite lands.

## Ideas

Statuses: `candidate` → `experimenting` → `promoted` / `parked` / `blocked` /
`retired` / `rejected`.

- `blocked` — never started; a named prerequisite (data, schema, gear) is
  missing. No experiment file.
- `promoted` — passed the lab and handed to a package or the root session; the
  experiment file stays as evidence.
- `parked` — tested; evidence exists but the result is inconclusive or
  deferred. The experiment file is kept; revisit when the named condition
  changes.
- `retired` — superseded by a schema or data change before it ran; kept for
  context, no experiment file.
- `rejected` — tested and failed; the file is deleted and a card is drafted.

| Idea | Question | Status | Experiment | Updated |
|---|---|---|---|---|
| Durability / decoupling | Do I fade within long runs, and is durability improving? | candidate | — | 2026-11-13 |
| Efficiency vs duration (start-up + drift) | Is session efficiency duration-dependent, and do a start-up term and drift explain it? | parked | `efficiency_duration.py` | 2026-11-13 |
| Efficiency line shape and confounders | Is the HR-speed line linear, does another curve fit better, and how much do terrain, weather and duration tighten the scatter? | promoted | `efficiency_line_shape.py` | 2026-11-17 |
| Efficiency frontier (best-run envelope) | Does the best-case pace/HR envelope track fitness more consistently than the average efficiency? | rejected | — | 2026-11-13 |
| Work-interval efficiency | Does efficiency hold in the work reps once warm-up and recovery are excluded? (superseded: subT/LT1 work-rep efficiency already exists) | retired | — | 2026-11-17 |
| Aerobic-threshold pace trend | How fast am I at a fixed HR, and is it moving? (needs efforts near threshold or streams) | parked | `aerobic_threshold.py` | 2026-11-13 |
| Threshold pace trend (athlete_thresholds) | Does the Intervals threshold pace / LTHR series move, and how does it compare with steady-run efficiency? | parked | `threshold_pace.py` | 2026-11-17 |
| LT1/LT2 estimation | Can LT1 and LT2 be estimated from training data (HR/pace, interval sets, efficiency) now that LTHR and threshold-pace snapshots exist? (vague) | candidate | — | 2026-11-16 |
| Race-derived fitness bundle | What do races imply for VDOT, critical speed, and my Riegel exponent? (37 official results plus 28 race logs; lab verdict only for now) | parked | `race_fitness.py` | 2026-11-19 |
| Riegel shape vs level | Can a two-timescale fit beat the free fit for current-form predictions? (37 official results; still thin for a two-timescale fit) | candidate | — | 2026-11-19 |
| Race prediction history | How have race-time predictions at standard distances evolved over time, and do they track actual results? (37 official results; startable, still noisy) | candidate | — | 2026-11-19 |
| Race plans | What should a race plan (pacing, zones, taper) look like from the training history, and how did past plans execute? (vague; needs event links: only 2) | blocked | — | 2026-11-19 |
| Garmin VO2max jumps | Why do the readings jump — terrain or device history? (sport-specific values are handled; canonical elevation and max HR are available) | candidate | `vo2max_jumps.py` | 2026-11-16 |
| Recovery → performance | Does HRV/RHR/sleep predict the next session's pace-adjusted efficiency? | candidate | — | 2026-11-13 |
| Elevation data check | Do summed lap ascents agree with Intervals gain/loss before v11? (superseded: elevation is canonical since v12) | retired | — | 2026-11-16 |
| Shoe impact | Do shoes change pace at matched HR, once gear coverage and confounders are handled? (2022+ gear is now linked: 26 shoes, 3,365 links) | candidate | — | 2026-11-19 |
| Polarization index | How polarized is my zone distribution, and does it beat the Z3+4 share? | candidate | — | 2026-11-13 |
| Load vs RPE | Where does `training_load` disagree with perceived effort? | candidate | — | 2026-11-13 |
| Cross-training load transfer | How much should cycling/cross load count toward running fitness, and does total load mislead during cycling-heavy phases? | promoted | `cross_training_load.py` | 2026-11-17 |
| Monotony / strain | Do weekly monotony and strain add signal over the load EWMAs? | candidate | — | 2026-11-13 |
| HR/economy-based VO2max | Can HR and running economy derive a Runalyze-style effective VO2max for 2023+ (where the Runalyze payload omits it) to compare with Garmin? (weight exists for 2024–2026, max HR is canonical) | promoted | `vo2max_estimates.py` | 2026-11-19 |
| Weather / temperature correlations | How much do temperature and season move pace, HR, efficiency, and RPE? (temperature is canonical; the Runalyze weather fields are still not mapped) | candidate | — | 2026-11-19 |
| GAP metrics | What is grade-adjusted pace, and does it change efficiency conclusions? (needs a pointwise grade profile; activity gain/loss is not enough) | blocked | — | 2026-11-16 |
| Route shape classification | Can routes be categorized as loop, out-and-back, point-to-point, or other? (vague; needs route geometry/streams, the routes table has no coordinates) | blocked | — | 2026-11-16 |

### Promoted notes
- **HR/economy-based VO2max** — promoted 2026-11-19. Session-level effective
  estimate: `VO2 = 3.5 + 0.2·speed_m_min`, divided by `HR / max_HR`. On 498
  steady runs the mean is 60.9 vs Garmin 61.5 and Runalyze 61.3 (stored with
  its 0.93 correction; the uncorrected mean is 65.9, so the estimate aligns
  with the corrected value). Garmin smoothing is device-specific: FR645 changed
  607 of 892 runs (mean |Δ| 0.449), Enduro 245 of 1,340 (0.067); Runalyze
  changed 489 of 497 (3.50) because it uses all runs. Smoothed vs Garmin:
  estimate 42d r=+0.80 / RMSE 1.51 and 90d +0.83 / 1.44; Runalyze 42d +0.75 /
  1.79 and 90d +0.78 / 1.63. All-runs sensitivity (closer to Runalyze's
  all-run input, but still raw pace): n=1,350, mean 60.4, r Runalyze +0.95,
  42d r Garmin +0.90; steady-only is +0.90 / +0.80. Runalyze's GAP is not
  reproduced, so hilly and interval runs are not like-for-like.
  The HR-reserve variant overestimates (~73.5) and is rejected.
  Against Daniels race VDOT on 19 road races since 2024: race VDOT mean 61.5 /
  median 61.8; Garmin 62.5 / 62.2; Runalyze 66.8 / 66.3; the nearest-run
  estimate 61.5. VDOT − Garmin is −1.0 / −1.1, VDOT − Runalyze −5.3 / −4.9,
  VDOT − estimate −0.2 / −0.1. The estimate is therefore in line with race
  fitness overall and much closer than Runalyze, though Garmin and the estimate
  run 2–3 units high on the sharp 2026 10k efforts.
  Handoff: candidate for a reports metric/card using the HR/HRmax formula and a
  42–90 day mean; it needs a max-HR source and the steady-run guard. Caveats:
  approximate ACSM economy, Garmin’s own smoothing, no streams, and the
  2026 level gap (estimate 61.7 vs Garmin 63.5). Evidence:
  `experiments/vo2max_estimates.py`; plots `vo2max-estimates.png`,
  `vo2max-estimate-scatter.png`, `vo2max-race-validation.png`.

- **Efficiency line shape and confounders** — promoted 2026-11-17. The
  current line through resting HR beats free linear, quadratic, log and
  piecewise forms in time-CV; the offset-quadratic term is not supported
  (`c = -0.26 bpm/(m/s)²`, 95% CI `-1.01..+0.34`). Adding session mix and
  elevation cuts time-CV RMSE by ~0.5 bpm (7.46 → 6.98); temperature adds
  nothing incremental and year only overfits. Handoff: document the small
  session/elevation caveat in the efficiency/HR-speed card; no curved line and
  no reports code change. Evidence: `experiments/efficiency_line_shape.py`.
  Revisited 2026-11-19 with the canonical Activity elevation fields: 502 steady
  rows with elevation. `current+v²` still adds nothing (time-CV 6.08 vs 6.03);
  `+elevation` improves in-sample RMSE 5.94 → 5.89 but worsens time-CV to 6.07,
  and `+v²+elevation` is 6.12. Terrain slopes are close (flat 24.55, rolling
  24.63, hilly 25.37 bpm per m/s) with RMSE 6.33/5.91/5.02. The conclusion is
  unchanged: elevation does not justify a curved or controlled line. Plot:
  `efficiency-line-terrain.png`.
- **Cross-training load transfer** — promoted 2026-11-17. Cross load is 9–26%
  of annual load, but 42-day running and cross loads correlate weakly with
  steady efficiency (raw +0.04 / −0.06; year-adjusted +0.05 / −0.04). Adding
  cross load does not improve the model (R² 0.074, cross coefficient negative,
  bootstrap `k` −10..+25), and the transfer grid's best `k` is **0.0** (R² flat
  0.071–0.073). Weeks with ≥20% cross load show slightly lower efficiency
  (2.409 vs 2.445), but this is confounded. Handoff: use running-only load for
  the running-fitness series and keep cross load as context; do not apply a
  positive transfer factor. Load starts in 2019 and efficiency in 2022, so the
  cycling-heavy 2020 phase is not covered; the load signal itself is weak, so
  this rejects a positive factor rather than proving a physiological one.
  Evidence: `experiments/cross_training_load.py`.

### Rejected

- **Efficiency frontier (best-run envelope)** — top-quartile quarterly
  efficiency (equal-n, 590 steady runs, 2022Q4–2026Q4) is smoother in level
  (SD 0.073 vs 0.086) but less reliable (split-half 0.60 vs 0.75) and tracks
  the trend less well (slope 0.024 vs 0.042 per year, R² 0.18 vs 0.39); no
  top-share from 10% to 50% beats the average. Sample-size bias was absent
  (raw-frontier correlation with quarter n was −0.19, not positive). The
  frontier is a stable level shift, not additional signal. Evidence:
  `git show 143267d:experiments/efficiency_frontier.py`.

### Parked notes

- **Efficiency vs duration** — tested on 980 steady runs: long runs read about
  4% low at 120 min and 8.5% low at 180 min versus 60 min, while the short-run
  dip is recovery-run composition, not a warm-up transient. Filtering does not
  improve the trend (split-half 0.75 → 0.48). The correction is deferred until
  streams or a heat/fatigue control reduce its uncertainty. Evidence:
  `experiments/efficiency_duration.py`.
- **Aerobic-threshold pace trend** — the fixed-HR index improved by roughly
  20–25 s/km at 140 bpm (5:11 to 4:08, 2022Q4–2026Q4), but 140 bpm was outside
  the observed steady-run HR range in 5 of 17 quarters, and the quarterly
  index correlates −0.55 to −0.71 with duration and −0.55 with resting HR.
  The trend survives a 40–75 min restriction (+0.188 m/s per year), so it is
  not only a mix artifact, but the index is not clean enough to promote.
  Revisit with tempo/threshold efforts that cover the reference HR, or with
  streams. Evidence: `experiments/aerobic_threshold.py`.
- **Threshold pace trend (athlete_thresholds)** — tested: the setting moved
  3:38 → 3:26 min/km (2019–2026), 10 of 13 changes occurred within ±14 days of
  a race or hard session, and quarterly efficiency correlates +0.67 with
  threshold speed. Threshold-target work reps are 15–22 s/km slower than the
  setting (HR ~164 vs LTHR 174); 9% of 934 reps go faster than the setting or
  above LTHR, with a median overshoot of 4.7 s/km and 3 bpm (p90 15.9 s/km and
  7 bpm). Session averages stay below the setting (+15.8 s/km, +9.7 bpm), and
  execution is stable (HR SD 0.9 bpm, pace SD 5.4 s/km; rep HR 94–97% LTHR).
  subT/LT1 gives the useful contrast: 17% of reps are faster than the pace
  setting but only 0% exceed LTHR, so pace overshoots there are HR-lag/short-rep
  artefacts and HR is the meaningful ceiling. Session margins sit within ±3% /
  ±5% / ±10% of the pace setting for 22% / 31% / 66% of sessions (HR: 14% /
  24% / 51%). Setting vs measured correlates +0.81, relative changes +0.73.
  Strict criteria still call it mixed: the threshold target overshoots modestly
  but not tightly, and the setting behaves more like a reference/ceiling than a
  precise target. Revisit with official race results or efforts at LTHR.
  Evidence: `experiments/threshold_pace.py`.
- **Race-derived fitness bundle** — tested on 65 race logs (37 result rows +
  28 sheet/race-log rows), with elevation classification. After excluding 3
  trail, 1 ultra, 1 relay and 8 hill races, 52 remain: CS 3.85 m/s
  (4:20/km), D′ 1,635 m, Riegel b 1.099, both R² 0.99; leave-one-out median
  errors 1.2 min (3.2%) for Riegel and 2.2 min (5.6%) for CS. Result-row-only
  sensitivity gives CS 4.05 m/s and b 1.085, so the older race logs shift the
  model modestly. Current-form equivalents use the dashboard method: the
  exponent is fitted over **all 65 race activities** (b=1.0798) and the line is
  anchored to the latest road 10k. That gives 5k 16.3, 10k 34.4, HM 1:17.0,
  M 2:42.7. Against the latest actual race in each bucket it has **1.4 min mean
  / 0.2 min median error**, versus 2.9/0.9 for the filtered exponent (b=1.099),
  4.1/1.8 for the latest-five level and 6.6/3.7 for the free global fit.
  Walk-forward over 19 races since 2024: dashboard all-b/latest-10k **1.0 mean /
  0.4 median**; 2y b/latest-10k 2.6/0.4 with +2.4 min bias (too slow);
  2y b/best-two 1.5/0.6; all-b/best-two 0.8/0.4, 89% within 1 min. The
  **two-year exponent is not supported**; all-history exponent plus a best-two
  anchor is marginally the best tested, but it is selection-biased and the
  sample is small. Keep the dashboard's all-history exponent and latest-10k
  anchor.
  VDOT vs Garmin: n=34, r=+0.73, median difference −1.1.
  Coherent enough to be useful, but this is a **lab verdict only**: no card or
  report handoff. Caveats: generic older names, 11 unknown-elevation races,
  and elevation-based exclusions. Evidence: `experiments/race_fitness.py`.

### Retired notes

- **Work-interval efficiency** — retired 2026-11-17: already implemented for
  subT/LT1 through `subt_work_points` / `subt_session_point`, and rendered in
  the subT report, subT EWMA, session report and subT chart. 156 of 159
  sessions with `subthreshold` or `lt1` targets are name-matched, so a
  target-based selection would add almost nothing. The remaining interval
  workouts are VO2max/speed/fartlek, where work-rep efficiency is
  intensity-specific and not comparable to aerobic efficiency.
