# Package instructions: hobbyjogging-reports

Analysis, Markdown reports, charts and the dashboard. The shared rules are in
the repo's `docs/AGENTS.md`; this file only adds package workflow.

## Dashboard changes

- After any dashboard or chart change, rebuild the real dashboard from the
  repo root with `./dashboard.sh --no-open`.
- Do not build a scratch copy or check the rendered dashboard; the unit tests
  are the verification unless the user asks for a visual check.

## CLI parity

- The dashboard is a rendered composition of console output: every card and
  page must have a `reports.sh` or `charts.sh` equivalent that produces the
  same numbers, as Markdown for tables and reports and a chart where the card
  is a chart.
- Add or extend the CLI side in the same change and share the
  analysis/formatting code. Never put dashboard-only analysis or formatting
  in the dashboard.
