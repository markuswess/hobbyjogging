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
- **Disposition.** Every idea ends as promote handoff, park (name the missing
  data or schema), or reject (delete the file). No open-ended results.
- **Cards.** The lab drafts promoted/rejected card text; the root session
  writes and commits the card in `docs/METRICS.md`.
- **Commits.** Finished experiments are committed here; never stage unrelated
  in-progress edits; do not push.
- **Minimal.** The smallest experiment that settles the question.

## Ideas

Statuses: `candidate` → `experimenting` → `promoted` / `parked` / `rejected`.

| Idea | Question | Status | Experiment | Updated |
|---|---|---|---|---|
| Durability / decoupling | Do I fade within long runs, and is durability improving? | candidate | — | 2026-11-13 |
| Efficiency vs duration (start-up + drift) | Is session efficiency duration-dependent, and do a start-up term and drift explain it? | parked | `efficiency_duration.py` | 2026-11-13 |
| Efficiency frontier (best-run envelope) | Does the best-case pace/HR envelope track fitness more consistently than the average efficiency? | rejected | — | 2026-11-13 |
| Work-interval efficiency | Does efficiency hold in the work reps once warm-up and recovery are excluded? | candidate | — | 2026-11-13 |
| Aerobic-threshold pace trend | How fast am I at a fixed HR, and is it moving? | candidate | — | 2026-11-13 |
| Race-derived fitness bundle | What do races imply for VDOT, critical speed, and my Riegel exponent? | candidate | — | 2026-11-13 |
| Recovery → performance | Does HRV/RHR/sleep predict the next session's pace-adjusted efficiency? | candidate | — | 2026-11-13 |
| Elevation data check | Do summed lap ascents agree with Intervals gain/loss before v11? | candidate | — | 2026-11-13 |
| Polarization index | How polarized is my zone distribution, and does it beat the Z3+4 share? | candidate | — | 2026-11-13 |
| Load vs RPE | Where does `training_load` disagree with perceived effort? | candidate | — | 2026-11-13 |
| Monotony / strain | Do weekly monotony and strain add signal over the load EWMAs? | candidate | — | 2026-11-13 |
| HR/economy-based VO2max | Can HR and running economy derive VO2max to compare with Garmin? (needs canonical weight and max HR) | parked | — | 2026-11-13 |
| Weather / temperature correlations | How much do temperature and season move pace, HR, efficiency, and RPE? (needs canonical temperature; wind/rain/clouds are empty) | parked | — | 2026-11-13 |
| GAP metrics | What is grade-adjusted pace, and does it change efficiency conclusions? (needs canonical elevation) | parked | — | 2026-11-13 |
