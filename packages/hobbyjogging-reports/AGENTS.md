# Package instructions: hobbyjogging-reports

Analysis, Markdown reports, charts and the dashboard. The shared rules are in
the repo's `docs/AGENTS.md`; this file only adds package workflow.

## Dashboard changes

- After any dashboard or chart change, rebuild the real dashboard from the
  repo root with `./dashboard.sh --no-open`.
- Do not build a scratch copy or check the rendered dashboard; the unit tests
  are the verification unless the user asks for a visual check.
