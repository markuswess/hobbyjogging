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
`rejected`.

- `blocked` — never started; a named prerequisite (data, schema, gear) is
  missing. No experiment file.
- `parked` — tested; evidence exists but the result is inconclusive or
  deferred. The experiment file is kept; revisit when the named condition
  changes.
- `rejected` — tested and failed; the file is deleted and a card is drafted.

| Idea | Question | Status | Experiment | Updated |
|---|---|---|---|---|
| Durability / decoupling | Do I fade within long runs, and is durability improving? | candidate | — | 2026-11-13 |
| Efficiency vs duration (start-up + drift) | Is session efficiency duration-dependent, and do a start-up term and drift explain it? | parked | `efficiency_duration.py` | 2026-11-13 |
| Efficiency frontier (best-run envelope) | Does the best-case pace/HR envelope track fitness more consistently than the average efficiency? | rejected | — | 2026-11-13 |
| Work-interval efficiency | Does efficiency hold in the work reps once warm-up and recovery are excluded? | candidate | — | 2026-11-13 |
| Aerobic-threshold pace trend | How fast am I at a fixed HR, and is it moving? (needs efforts near threshold or streams) | parked | `aerobic_threshold.py` | 2026-11-13 |
| LT1/LT2 estimation | Can LT1 and LT2 be estimated from training data (HR/pace, interval sets, efficiency), and how do they move? (vague) | candidate | — | 2026-11-13 |
| Race-derived fitness bundle | What do races imply for VDOT, critical speed, and my Riegel exponent? | candidate | — | 2026-11-13 |
| Riegel shape vs level | Can a two-timescale fit beat the free fit for current-form predictions? (needs more races spanning the distances) | blocked | — | 2026-11-13 |
| Race prediction history | How have race-time predictions at standard distances evolved over time, and do they track actual results? (needs more races spanning the distances) | blocked | — | 2026-11-13 |
| Race plans | What should a race plan (pacing, zones, taper) look like from the training history, and how did past plans execute? (vague) | candidate | — | 2026-11-13 |
| Garmin VO2max jumps | Why do the readings jump — sport-specific values, terrain, or device history? (revisit with canonical elevation data) | parked | `vo2max_jumps.py` | 2026-11-13 |
| Recovery → performance | Does HRV/RHR/sleep predict the next session's pace-adjusted efficiency? | candidate | — | 2026-11-13 |
| Elevation data check | Do summed lap ascents agree with Intervals gain/loss before v11? | candidate | — | 2026-11-13 |
| Shoe impact | Do shoes change pace at matched HR, once gear coverage and confounders are handled? (needs 2022+ gear) | blocked | — | 2026-11-13 |
| Polarization index | How polarized is my zone distribution, and does it beat the Z3+4 share? | candidate | — | 2026-11-13 |
| Load vs RPE | Where does `training_load` disagree with perceived effort? | candidate | — | 2026-11-13 |
| Monotony / strain | Do weekly monotony and strain add signal over the load EWMAs? | candidate | — | 2026-11-13 |
| HR/economy-based VO2max | Can HR and running economy derive VO2max to compare with Garmin? (needs canonical weight and max HR) | blocked | — | 2026-11-13 |
| Weather / temperature correlations | How much do temperature and season move pace, HR, efficiency, and RPE? (needs canonical temperature; wind/rain/clouds are empty) | blocked | — | 2026-11-13 |
| GAP metrics | What is grade-adjusted pace, and does it change efficiency conclusions? (needs canonical elevation) | blocked | — | 2026-11-13 |

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
- **Garmin VO2max jumps** — tested: 62% of all jumps happen at a sport switch
  (run/ride share one column), running-only jumps are concentrated in
  2019–2022, and the terrain question needs canonical elevation data before it
  can be settled. Evidence: `experiments/vo2max_jumps.py`.
- **Aerobic-threshold pace trend** — the fixed-HR index improved by roughly
  20–25 s/km at 140 bpm (5:11 to 4:08, 2022Q4–2026Q4), but 140 bpm was outside
  the observed steady-run HR range in 5 of 17 quarters, and the quarterly
  index correlates −0.55 to −0.71 with duration and −0.55 with resting HR.
  The trend survives a 40–75 min restriction (+0.188 m/s per year), so it is
  not only a mix artifact, but the index is not clean enough to promote.
  Revisit with tempo/threshold efforts that cover the reference HR, or with
  streams. Evidence: `experiments/aerobic_threshold.py`.
