# Experiments

Throwaway analysis for a metric idea. Nothing here is imported by a package,
tested, or wired into a report.

```bash
cp experiments/template.py experiments/<name>.py
uv run --env-file .env python experiments/<name>.py
```

Rules:

- One file per idea, self-contained and runnable; copy
  [`template.py`](template.py).
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

## Where the notebook lives

The experiment scripts, the candidate table and the findings are personal and
live outside this repository, in `~/projects/laufen_private/lab/` for this
athlete. Set `HOBBYJOGGING_LAB_DIR` to that directory; it defaults to
`experiments/` so a fresh clone still has a working bench:

```bash
export HOBBYJOGGING_LAB_DIR=~/projects/laufen_private/lab
cd ~/projects/hobbyjogging
uv run --env-file .env python "$HOBBYJOGGING_LAB_DIR/<name>.py"
```

The dashboard's Lab tab reads `$HOBBYJOGGING_LAB_DIR`; a demo build never does
and shows these bench rules only.

## Lab session ground rules

- **Scope.** The lab explores; promotion is a package/root step. Writes stay
  in the lab directory and its notebook; never package code, schema, or
  reports.
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
- **Commits.** Finished experiments are committed in the private lab repo;
  never stage unrelated in-progress edits; do not push.
- **Minimal.** The smallest experiment that settles the question.
- **Impact per unit of effort.** Pick the highest-impact, lowest-workload idea
  next; the list order is not a schedule. An idea that unblocks or invalidates
  other measurements outranks a new one. Blocked items stay out of the queue
  until their prerequisite lands.
